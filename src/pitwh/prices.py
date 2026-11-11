"""Tiingo end-of-day prices: client, raw cache, and Parquet landing."""

import json
import logging
import os
import random
import time
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pitwh import config
from pitwh.client import JsonClient, fetch_cached

log = logging.getLogger(__name__)

PRICES_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
META_URL = "https://api.tiingo.com/tiingo/daily/{symbol}"
SUPPORTED_URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"

# Starter plan: 50 requests per hour. Staying a little under leaves room for
# a manual request without tripping the hourly limit mid-run.
STARTER_RATE = 45 / 3600

# One session of history before START_DATE so the first in-window daily
# return has a previous close.
PRICE_START = "2014-12-01"


class TiingoClient(JsonClient):
    def __init__(
        self,
        token: str,
        rate: float = STARTER_RATE,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not token:
            raise ValueError("TIINGO_API_KEY is not set")
        # Header, not the `token` query parameter: httpx logs request URLs.
        super().__init__({"Authorization": f"Token {token}"}, rate, transport, sleep)

    @classmethod
    def from_env(cls) -> "TiingoClient":
        return cls(os.environ.get("TIINGO_API_KEY", ""))


def tiingo_symbol(ticker: str) -> str:
    """S&P lists share classes as BF.B; Tiingo uses BF-B."""
    return ticker.replace(".", "-")


def fetch_meta(client: TiingoClient, symbol: str, raw_dir: Path, refresh: bool = False) -> dict:
    url = META_URL.format(symbol=symbol)
    return fetch_cached(client, url, raw_dir / "meta" / f"{symbol}.json", refresh)


def fetch_meta_name(client: TiingoClient, symbol: str, raw_dir: Path) -> str | None:
    try:
        return fetch_meta(client, symbol, raw_dir).get("name")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        return None


def supported_tickers(raw_dir: Path, refresh: bool = False) -> pd.DataFrame:
    """Tiingo's coverage list (one row per ticker per company), US-dollar stocks only."""
    path = raw_dir / "supported_tickers.zip"
    if refresh or not path.exists():
        resp = httpx.get(SUPPORTED_URL, timeout=60.0)
        resp.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
    df = pd.read_csv(path, keep_default_na=False)
    return df[(df["assetType"] == "Stock") & (df["priceCurrency"] == "USD")]


def ingest_prices(
    client: TiingoClient, symbols: Iterable[str], raw_dir: Path, refresh: bool = False
) -> list[str]:
    """Fetch full daily history per symbol. Returns the symbols Tiingo does not know."""
    missing = []
    for symbol in symbols:
        try:
            fetch_cached(
                client,
                PRICES_URL.format(symbol=symbol),
                raw_dir / "prices" / f"{symbol}.json",
                refresh,
                params={"startDate": PRICE_START},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            log.warning("Tiingo has no prices for %s", symbol)
            missing.append(symbol)
    return missing


PRICES_SCHEMA = pa.schema(
    [
        ("ticker", pa.string()),
        ("trade_date", pa.date32()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
        ("adj_close", pa.float64()),
        ("div_cash", pa.float64()),
        ("split_factor", pa.float64()),
    ]
)

COLUMNS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "adjClose": "adj_close",
    "divCash": "div_cash",
    "splitFactor": "split_factor",
}


def synthetic_prices(sessions: list[date], actions: pd.DataFrame, seed: int) -> list[dict]:
    """A Tiingo-shaped daily series on a seeded random walk, with the given
    dividends and splits applied on their real dates.

    Tiingo's free plan licenses its data for internal use only, so the
    committed CI fixtures are synthetic. The adjusted close is back-adjusted
    with the convention the real data was confirmed to follow (see
    docs/decisions.md): each day's adjusted ratio is (close + div) * split /
    previous close.
    """
    rng = random.Random(seed)
    events = {
        d: (float(div), float(split))
        for d, div, split in actions[["date", "div_cash", "split_factor"]].itertuples(index=False)
    }
    closes, prev = [], 100.0
    for day in sessions:
        div, split = events.get(day, (0.0, 1.0))
        prev = max(round(prev * (1 + rng.gauss(0.0003, 0.015)) / split - div, 2), 0.01)
        closes.append(prev)
    adj = [closes[-1]]
    for i in range(len(sessions) - 1, 0, -1):
        div, split = events.get(sessions[i], (0.0, 1.0))
        adj.append(adj[-1] / ((closes[i] + div) * split / closes[i - 1]))
    adj.reverse()
    rows = []
    for i, day in enumerate(sessions):
        div, split = events.get(day, (0.0, 1.0))
        open_ = closes[i - 1] / split if i else closes[i]
        rows.append(
            {
                "date": f"{day.isoformat()}T00:00:00.000Z",
                "open": round(open_, 2),
                "high": round(max(open_, closes[i]) * 1.005, 2),
                "low": round(min(open_, closes[i]) * 0.995, 2),
                "close": closes[i],
                "volume": rng.randrange(1_000_000, 50_000_000),
                "adjClose": adj[i],
                "divCash": div,
                "splitFactor": split,
            }
        )
    return rows


def write_synthetic_price_fixtures(tiingo_dir: Path, sessions: list[date], seed: int) -> list[str]:
    """Write prices/<symbol>.json for each row of symbols.csv from corporate_actions.csv."""
    symbols = pd.read_csv(tiingo_dir / "symbols.csv", parse_dates=["first_date", "last_date"])
    actions = pd.read_csv(tiingo_dir / "corporate_actions.csv", parse_dates=["date"])
    actions["date"] = actions["date"].dt.date
    out = tiingo_dir / "prices"
    out.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(symbols.itertuples(index=False)):
        days = [d for d in sessions if s.first_date.date() <= d <= s.last_date.date()]
        rows = synthetic_prices(days, actions[actions.symbol == s.symbol], seed + i)
        # One row per line keeps fixture diffs readable.
        body = ",\n".join(json.dumps(r, separators=(",", ":")) for r in rows)
        (out / f"{s.symbol}.json").write_text(f"[\n{body}\n]\n")
    return list(symbols.symbol)


def land_prices(raw_dir: Path, out: Path) -> int:
    frames = []
    for path in sorted(raw_dir.glob("*.json")):
        rows = json.loads(path.read_text())
        if not rows:
            continue
        df = pd.DataFrame(rows)[["date", *COLUMNS]].rename(columns=COLUMNS)
        # Tiingo stamps EOD bars at midnight UTC; the date part is the session.
        df["trade_date"] = pd.to_datetime(df.pop("date")).dt.date
        df.insert(0, "ticker", path.stem)
        frames.append(df)
    df = pd.concat(frames) if frames else pd.DataFrame(columns=PRICES_SCHEMA.names)
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(
        df[PRICES_SCHEMA.names], schema=PRICES_SCHEMA, preserve_index=False
    )
    pq.write_table(table, out)
    return len(df)


def land_all(
    raw_dir: Path = config.RAW_DIR / "tiingo" / "prices", out_dir: Path = config.PARQUET_DIR
) -> int:
    return land_prices(raw_dir, out_dir / "prices_daily.parquet")
