"""Tiingo end-of-day prices: client, raw cache, and Parquet landing."""

import json
import logging
import os
import time
from collections.abc import Callable, Iterable
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
