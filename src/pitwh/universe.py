"""Historical S&P 500 membership and the reproducible security sample."""

import random
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from pitwh import config, prices, sec

# fja05680/sp500 (MIT). Pinned so the sample is reproducible.
SP500_COMMIT = "a2430f2af0c79ddf0748e91de11bdeb1616ab5a7"
SP500_URL = (
    f"https://raw.githubusercontent.com/fja05680/sp500/{SP500_COMMIT}/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
)


def membership_intervals(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Turn dated constituent snapshots into (ticker, start_date, end_date) intervals.

    end_date is the first snapshot date on which the ticker is absent (exclusive),
    or null if it is still a member in the last snapshot.
    """
    snaps = snapshots.assign(date=pd.to_datetime(snapshots["date"]).dt.date).sort_values("date")
    dates = list(snaps["date"])
    open_since: dict[str, date] = {}
    rows = []
    for d, tickers in zip(dates, snaps["tickers"], strict=True):
        current = set(tickers.split(","))
        for t in current - open_since.keys():
            open_since[t] = d
        for t in open_since.keys() - current:
            rows.append((t, open_since.pop(t), d))
    rows.extend((t, start, None) for t, start in open_since.items())
    out = pd.DataFrame(rows, columns=["ticker", "start_date", "end_date"])
    return out.sort_values(["ticker", "start_date"]).reset_index(drop=True)


def in_window(intervals: pd.DataFrame, start: date = config.START_DATE) -> pd.DataFrame:
    keep = intervals["end_date"].isna() | (intervals["end_date"] > start)
    return intervals[keep].reset_index(drop=True)


def load_snapshots(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"tickers": str})


PERIODIC_FORMS = frozenset({"10-K", "10-Q", "10-KT", "20-F", "40-F"})

# A 10-K for the last fiscal year can land a few months after a company leaves.
FILING_SLACK = timedelta(days=120)


def _periodic_in(filings: pd.DataFrame, start: date, end: date | None) -> pd.DataFrame:
    last = (end or date.today()) + FILING_SLACK
    keep = filings["form"].isin(PERIODIC_FORMS) & filings["filing_date"].between(start, last)
    return filings[keep]


def filed_during(filings: pd.DataFrame, start: date, end: date | None) -> bool:
    """True if the filer submitted a 10-K/10-Q while the ticker was in the index."""
    return not _periodic_in(filings, start, end).empty


def filenames_cite(filings: pd.DataFrame, ticker: str, start: date, end: date | None) -> bool:
    """True if a periodic filing in the window is named after `ticker` (fb-20211231.htm).

    Filers name XBRL documents after their own ticker, which links an old ticker
    to a renamed company without trusting a name lookup.
    """
    t = re.escape(ticker.lower().replace(".", ""))
    # One-letter tickers collide with other filers' date-prefixed names
    # (a201410-k.htm), so they need an explicit separator.
    pattern = re.compile(rf"^{t}[-_]" if len(ticker) == 1 else rf"^{t}([-_]|\d)")
    docs = _periodic_in(filings, start, end)["primary_document"].str.lower()
    return bool(docs.map(lambda d: bool(pattern.match(d))).any())


LEGAL_WORDS = frozenset(
    [
        "THE",
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "CO",
        "COMPANY",
        "LTD",
        "LIMITED",
        "PLC",
        "LLC",
        "LP",
        "NV",
        "SA",
        "AG",
        "HOLDINGS",
        "HOLDING",
        "GROUP",
        "DE",
        "MD",
        "NEW",
        "CLASS",
        "COMMON",
        "STOCK",
        "AND",
    ]
)


def _name_tokens(name: str) -> frozenset[str]:
    words = re.sub(r"[^A-Z0-9]+", " ", name.upper()).split()
    return frozenset(w for w in words if w not in LEGAL_WORDS)


def names_match(a: str, b: str) -> bool:
    ta, tb = _name_tokens(a), _name_tokens(b)
    return bool(ta and tb) and (ta <= tb or tb <= ta)


def price_coverage(
    supported: pd.DataFrame,
    symbol: str,
    start: date,
    end: date | None,
    today: date | None = None,
    tolerance: timedelta = timedelta(days=10),
) -> bool:
    """True if the price history Tiingo serves for `symbol` spans start..end.

    Tiingo lists a reused ticker once per company but serves only the one
    still trading, so coverage is judged on the row with the latest end date
    (latest start date on a tie). A renamed company's row can start earlier
    than the old holder's (COR: Cencora from 1995, CoreSite 2010-2021).
    """
    rows = supported[supported["ticker"] == symbol]
    if rows.empty:
        return False
    order = rows.assign(
        _end=pd.to_datetime(rows["endDate"]), _start=pd.to_datetime(rows["startDate"])
    )
    served = order.sort_values(["_end", "_start"]).iloc[-1]
    first = pd.Timestamp(served["startDate"]).date()
    last = pd.Timestamp(served["endDate"]).date()
    return first <= start + tolerance and last >= (end or today or date.today()) - tolerance


class UnresolvedTickers(RuntimeError):
    """Raised with the ticker intervals that need a row in ticker_cik_overrides.csv."""


Resolve = Callable[[str, date, date | None], int | None]
SameCompany = Callable[[str, date, date | None, int], bool]


def _opt(d) -> date | None:
    return None if pd.isna(d) else d


def select_universe(
    pool: pd.DataFrame,
    resolve: Resolve,
    same_company: SameCompany,
    seed: int = config.UNIVERSE_SEED,
    size: int = config.UNIVERSE_SIZE,
    min_departed: int = config.MIN_DEPARTED_SECURITIES,
) -> pd.DataFrame:
    """Draw a reproducible sample of securities (CIKs) with their ticker intervals.

    Departed tickers are drawn first until `min_departed` securities that are no
    longer members are in, then any ticker until `size` securities. A security
    keeps every ticker it traded under, so a rename is one security, not two.
    """
    pool = pool.sort_values(["ticker", "start_date"]).reset_index(drop=True)
    is_open = pool["end_date"].isna()
    current = set(pool.loc[is_open, "ticker"])
    rng = random.Random(seed)
    departed_order = sorted(set(pool["ticker"]) - current)
    rng.shuffle(departed_order)
    any_order = sorted(set(pool["ticker"]))
    rng.shuffle(any_order)

    cik_by_row: dict[int, int | None] = {}
    unresolved: list[str] = []

    def cik_of(i: int) -> int | None:
        if i not in cik_by_row:
            r = pool.loc[i]
            cik_by_row[i] = resolve(r.ticker, r.start_date, _opt(r.end_date))
            if cik_by_row[i] is None:
                unresolved.append(f"{r.ticker} from {r.start_date}")
        return cik_by_row[i]

    # Current members resolve cheaply from the SEC ticker map, and knowing who
    # holds each live ticker is what lets a departed ticker turn out to be a rename.
    holders: dict[int, set[int]] = defaultdict(set)
    for i in pool.index[is_open]:
        if (c := cik_of(i)) is not None:
            holders[c].add(i)

    members: dict[int, set[int]] = {}

    def expand(c: int) -> None:
        rows = members[c]
        rows |= holders[c]
        grew = True
        while grew:
            grew = False
            starts = {pool.at[i, "start_date"] for i in rows}
            for j in pool.index[pool["end_date"].isin(starts)]:
                if j in rows or cik_by_row.get(j, c) != c:
                    continue
                r = pool.loc[j]
                if same_company(r.ticker, r.start_date, r.end_date, c):
                    cik_by_row[j] = c
                    rows.add(j)
                    grew = True

    def add(ticker: str) -> None:
        for i in pool.index[pool["ticker"] == ticker]:
            if (c := cik_of(i)) is not None:
                members.setdefault(c, set()).add(i)
                expand(c)

    def n_departed() -> int:
        return sum(1 for rows in members.values() if pool.loc[list(rows), "end_date"].notna().all())

    def taken(ticker: str) -> bool:
        return any(pool.at[i, "ticker"] == ticker for rows in members.values() for i in rows)

    for t in departed_order:
        if n_departed() >= min_departed:
            break
        if not taken(t):
            add(t)
    for t in any_order:
        if len(members) >= size:
            break
        if not taken(t):
            add(t)

    if unresolved:
        raise UnresolvedTickers("no verified CIK for: " + ", ".join(unresolved))
    rows = [
        (c, *pool.loc[i, ["ticker", "start_date", "end_date"]])
        for c, idx in members.items()
        for i in idx
    ]
    out = pd.DataFrame(rows, columns=["cik", "ticker", "start_date", "end_date"])
    return out.sort_values(["cik", "start_date"]).reset_index(drop=True)


OVERRIDES_PATH = config.SEEDS_DIR / "ticker_cik_overrides.csv"


class Resolver:
    """Maps a ticker's membership interval to a CIK, accepting only verified matches.

    Order: hand-checked override, then the SEC's current ticker map, then the
    company name Tiingo gives for the ticker searched on EDGAR. Every automatic
    match must have filed a 10-K/10-Q while the ticker was in the index.
    """

    def __init__(
        self,
        sec_client: sec.SecClient,
        tiingo_client: prices.TiingoClient,
        sec_raw: Path = config.RAW_DIR / "sec",
        tiingo_raw: Path = config.RAW_DIR / "tiingo",
        overrides: Path = OVERRIDES_PATH,
    ):
        self.sec_client = sec_client
        self.tiingo_client = tiingo_client
        self.sec_raw = sec_raw
        self.tiingo_raw = tiingo_raw
        ov = pd.read_csv(overrides, parse_dates=["start_date"])
        self.overrides = {
            (r.ticker, r.start_date.date()): int(r.cik) for r in ov.itertuples(index=False)
        }
        # A negative ID marks a security that never filed with the SEC (e.g. a
        # bank that filed with the FDIC); its name comes from the override row.
        self.non_sec_names = {
            int(r.cik): r.name for r in ov.itertuples(index=False) if int(r.cik) < 0
        }
        tickers = sec.ingest_company_tickers(sec_client, sec_raw)
        self.sec_map = {v["ticker"].replace("-", "."): int(v["cik_str"]) for v in tickers.values()}
        self.method: dict[tuple[str, date], str] = {}
        self._filings: dict[int, tuple[str, pd.DataFrame]] = {}

    def filings(self, cik: int) -> tuple[str, pd.DataFrame]:
        if cik in self.non_sec_names:
            # Never filed with the SEC, so no filing can link another ticker to it.
            empty = pd.DataFrame(columns=["filing_date", "form", "primary_document"])
            return self.non_sec_names[cik], empty
        if cik not in self._filings:
            sec.ingest_submissions(self.sec_client, cik, self.sec_raw)
            self._filings[cik] = sec.periodic_filings(self.sec_raw, cik)
        return self._filings[cik]

    def name(self, cik: int) -> str:
        return self.filings(cik)[0]

    def _hit(self, key: tuple[str, date], cik: int, method: str) -> int:
        self.method[key] = method
        return cik

    def resolve(self, ticker: str, start: date, end: date | None) -> int | None:
        key = (ticker, start)
        if key in self.overrides:
            return self._hit(key, self.overrides[key], "override")

        mapped = self.sec_map.get(ticker)
        if mapped is not None:
            name, f = self.filings(mapped)
            # A live ticker belongs to its current holder by definition; a closed
            # one may have been reused, so it also needs the filename evidence.
            if filed_during(f, start, end) and (
                end is None or filenames_cite(f, ticker, start, end)
            ):
                return self._hit(key, mapped, "sec_map")

        tiingo_name = prices.fetch_meta_name(
            self.tiingo_client, prices.tiingo_symbol(ticker), self.tiingo_raw
        )
        if not tiingo_name:
            return None
        if mapped is not None:
            name, f = self.filings(mapped)
            if names_match(name, tiingo_name) and filed_during(f, start, end):
                return self._hit(key, mapped, "sec_map_name")
        for cik, entity in sec.search_entities(self.sec_client, tiingo_name, self.sec_raw)[:5]:
            if names_match(entity, tiingo_name) and filed_during(self.filings(cik)[1], start, end):
                return self._hit(key, cik, "name_search")
        return None

    def same_company(self, ticker: str, start: date, end: date | None, cik: int) -> bool:
        key = (ticker, start)
        if key in self.overrides:
            linked = self.overrides[key] == cik
            if linked:
                self.method[key] = "override"
            return linked
        if filenames_cite(self.filings(cik)[1], ticker, start, end):
            self.method[key] = "rename_filename"
            return True
        return False


def securities_table(
    members: pd.DataFrame,
    resolver: Resolver,
    supported: pd.DataFrame,
    start: date = config.START_DATE,
    window_end: date | None = None,
) -> pd.DataFrame:
    """One row per CIK: name, departure status, and the Tiingo symbol for its prices.

    A current member needs prices only up to window_end (the last membership
    snapshot): later delistings are outside the universe.
    """
    by_cik = {c: t for t, c in resolver.sec_map.items()}
    rows = []
    for cik, g in members.groupby("cik"):
        is_departed = bool(g["end_date"].notna().all())
        need_from = max(min(g["start_date"]), start)
        need_to = max(g["end_date"]) if is_departed else window_end
        # Tiingo files a renamed company's whole history under its newest ticker.
        candidates = [by_cik[cik]] if cik in by_cik else []
        candidates += list(g.sort_values("start_date", ascending=False)["ticker"])
        symbol = next(
            (
                prices.tiingo_symbol(t)
                for t in candidates
                if price_coverage(supported, prices.tiingo_symbol(t), need_from, need_to)
            ),
            None,
        )
        rows.append((cik, resolver.name(cik), is_departed, symbol))
    return pd.DataFrame(rows, columns=["cik", "name", "is_departed", "price_symbol"])


def fetch_snapshots(path: Path = config.RAW_DIR / "universe" / "historical.csv") -> Path:
    if not path.exists():
        resp = httpx.get(SP500_URL, timeout=60.0)
        resp.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
    return path


def fixture_tables(
    pool: pd.DataFrame, ciks: dict[str, int], names: dict[int, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Membership and securities rows for a fixed ticker->CIK set (offline CI fixtures).

    Same columns as build-universe writes, so the dbt sources read either.
    """
    members = pool[pool["ticker"].isin(ciks)].assign(
        cik=lambda d: d["ticker"].map(ciks), resolution="fixture"
    )[["cik", "ticker", "start_date", "end_date", "resolution"]]
    securities = (
        members.groupby("cik")
        .agg(is_departed=("end_date", lambda s: bool(s.notna().all())), ticker=("ticker", "last"))
        .reset_index()
        .assign(name=lambda d: d["cik"].map(names), price_symbol=lambda d: d["ticker"])
    )[["cik", "name", "is_departed", "price_symbol"]]
    return members.reset_index(drop=True), securities
