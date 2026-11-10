"""SEC EDGAR client, raw-response cache, and Parquet landing for facts and filings."""

import json
import logging
import os
import random
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pitwh import config

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/{name}"

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_TRIES = 5


class TokenBucket:
    """Blocks until a request may be sent at no more than `rate` per second."""

    # SEC allows 10 req/s. A bucket holding 8 tokens could send 8 at once and
    # then 8 more within the same second, so capacity stays at 1.
    def __init__(
        self,
        rate: float,
        capacity: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.clock = clock
        self.sleep = sleep
        self.last = clock()

    def _refill(self) -> None:
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now

    def acquire(self) -> None:
        self._refill()
        if self.tokens < 1:
            self.sleep((1 - self.tokens) / self.rate)
            self._refill()
        self.tokens -= 1


class SecClient:
    def __init__(
        self,
        user_agent: str,
        rate: float = 8.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT must include a name and contact email")
        self.http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=30.0,
            transport=transport,
        )
        self.bucket = TokenBucket(rate, sleep=sleep)
        self.sleep = sleep

    @classmethod
    def from_env(cls) -> "SecClient":
        return cls(os.environ.get("SEC_USER_AGENT", ""))

    def get_json(self, url: str) -> dict:
        for attempt in range(1, MAX_TRIES + 1):
            self.bucket.acquire()
            try:
                resp = self.http.get(url)
            except httpx.TransportError as exc:
                log.warning("SEC %s transport error on try %d: %s", url, attempt, exc)
            else:
                if resp.status_code not in RETRY_STATUSES:
                    resp.raise_for_status()
                    return resp.json()
                log.warning("SEC %s returned %d on try %d", url, resp.status_code, attempt)
            if attempt < MAX_TRIES:
                self.sleep(min(2**attempt, 60) * random.uniform(0.5, 1.0))
        raise RuntimeError(f"SEC request failed after {MAX_TRIES} tries: {url}")


def cik_name(cik: int) -> str:
    return f"CIK{cik:010d}.json"


def fetch_cached(client: SecClient, url: str, path: Path, refresh: bool = False) -> dict:
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    data = client.get_json(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)
    return data


def ingest_company_tickers(client: SecClient, raw_dir: Path, refresh: bool = False) -> dict:
    return fetch_cached(client, TICKERS_URL, raw_dir / "company_tickers.json", refresh)


def ingest_company(client: SecClient, cik: int, raw_dir: Path, refresh: bool = False) -> None:
    name = cik_name(cik)
    subs_dir = raw_dir / "submissions"
    subs = fetch_cached(client, SUBMISSIONS_URL.format(name=name), subs_dir / name, refresh)
    # Companies with long histories page older filings into extra files.
    for extra in subs.get("filings", {}).get("files", []):
        fname = extra["name"]
        fetch_cached(client, SUBMISSIONS_URL.format(name=fname), subs_dir / fname, refresh)

    try:
        fetch_cached(
            client, COMPANYFACTS_URL.format(name=name), raw_dir / "companyfacts" / name, refresh
        )
    except httpx.HTTPStatusError as exc:
        # Filers with no XBRL submissions have no companyfacts document.
        if exc.response.status_code != 404:
            raise
        log.warning("no companyfacts for CIK %d", cik)


FACTS_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("taxonomy", pa.string()),
        ("tag", pa.string()),
        ("unit", pa.string()),
        ("val", pa.float64()),
        ("period_start", pa.date32()),
        ("period_end", pa.date32()),
        ("fy", pa.int32()),
        ("fp", pa.string()),
        ("form", pa.string()),
        ("filed", pa.date32()),
        ("accn", pa.string()),
        ("frame", pa.string()),
    ]
)

FILINGS_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("accession_number", pa.string()),
        ("form", pa.string()),
        ("filing_date", pa.date32()),
        ("report_date", pa.date32()),
        ("acceptance_datetime", pa.string()),
    ]
)

COMPANIES_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("name", pa.string()),
        ("tickers", pa.list_(pa.string())),
        ("fiscal_year_end", pa.string()),
        ("sic_description", pa.string()),
    ]
)


def _wanted_tags(concept_map: Path) -> set[tuple[str, str]]:
    cm = pd.read_csv(concept_map)
    return set(zip(cm["taxonomy"], cm["tag"], strict=True))


def _fact_rows(doc: dict, wanted: set[tuple[str, str]]) -> Iterator[dict]:
    cik = int(doc["cik"])
    for taxonomy, tags in doc.get("facts", {}).items():
        for tag, body in tags.items():
            if (taxonomy, tag) not in wanted:
                continue
            for unit, facts in body["units"].items():
                for f in facts:
                    yield {
                        "cik": cik,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "val": f["val"],
                        "period_start": f.get("start"),
                        "period_end": f["end"],
                        "fy": f.get("fy"),
                        "fp": f.get("fp"),
                        "form": f.get("form"),
                        "filed": f.get("filed"),
                        "accn": f["accn"],
                        "frame": f.get("frame"),
                    }


def _write(rows: list[dict], schema: pa.Schema, out: Path) -> int:
    df = pd.DataFrame(rows, columns=schema.names)
    for field in schema:
        if pa.types.is_date32(field.type):
            df[field.name] = pd.to_datetime(df[field.name], errors="raise").dt.date
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False), out)
    return len(df)


def land_facts(raw_dir: Path, out: Path, concept_map: Path) -> int:
    wanted = _wanted_tags(concept_map)
    rows: list[dict] = []
    for path in sorted((raw_dir / "companyfacts").glob("CIK*.json")):
        rows.extend(_fact_rows(json.loads(path.read_text()), wanted))
    return _write(rows, FACTS_SCHEMA, out)


def _filing_rows(cik: int, block: dict) -> Iterator[dict]:
    for i, accn in enumerate(block["accessionNumber"]):
        yield {
            "cik": cik,
            "accession_number": accn,
            "form": block["form"][i],
            "filing_date": block["filingDate"][i],
            "report_date": block["reportDate"][i] or None,
            "acceptance_datetime": block["acceptanceDateTime"][i],
        }


def land_filings(raw_dir: Path, filings_out: Path, companies_out: Path) -> tuple[int, int]:
    filings: list[dict] = []
    companies: list[dict] = []
    subs_dir = raw_dir / "submissions"
    for path in sorted(subs_dir.glob("CIK??????????.json")):
        doc = json.loads(path.read_text())
        cik = int(doc["cik"])
        companies.append(
            {
                "cik": cik,
                "name": doc.get("name"),
                "tickers": doc.get("tickers", []),
                "fiscal_year_end": doc.get("fiscalYearEnd"),
                "sic_description": doc.get("sicDescription"),
            }
        )
        filings.extend(_filing_rows(cik, doc["filings"]["recent"]))
        for extra in doc["filings"].get("files", []):
            extra_path = subs_dir / extra["name"]
            filings.extend(_filing_rows(cik, json.loads(extra_path.read_text())))
    return (
        _write(filings, FILINGS_SCHEMA, filings_out),
        _write(companies, COMPANIES_SCHEMA, companies_out),
    )


def _filter_block(block: dict, keep: set[str]) -> dict:
    idx = [i for i, a in enumerate(block["accessionNumber"]) if a in keep]
    return {col: [vals[i] for i in idx] for col, vals in block.items()}


def trim_fixtures(raw_dir: Path, out_dir: Path, concept_map: Path) -> None:
    """Cut cached SEC responses down to mapped tags and the filings they cite.

    The output keeps the raw cache layout and the real response shapes, so the
    same landing code runs on it offline in CI.
    """
    wanted = _wanted_tags(concept_map)
    for facts_path in sorted((raw_dir / "companyfacts").glob("CIK*.json")):
        doc = json.loads(facts_path.read_text())
        kept: dict[str, dict] = {}
        accns: set[str] = set()
        for taxonomy, tags in doc.get("facts", {}).items():
            for tag, body in tags.items():
                if (taxonomy, tag) in wanted:
                    kept.setdefault(taxonomy, {})[tag] = body
                    accns.update(f["accn"] for facts in body["units"].values() for f in facts)
        _dump(out_dir / "companyfacts" / facts_path.name, {**doc, "facts": kept})

        subs_dir = raw_dir / "submissions"
        subs = json.loads((subs_dir / facts_path.name).read_text())
        files = []
        for extra in subs["filings"].get("files", []):
            block = _filter_block(json.loads((subs_dir / extra["name"]).read_text()), accns)
            if block["accessionNumber"]:
                _dump(out_dir / "submissions" / extra["name"], block)
                files.append({**extra, "filingCount": len(block["accessionNumber"])})
        recent = _filter_block(subs["filings"]["recent"], accns)
        _dump(
            out_dir / "submissions" / facts_path.name,
            {**subs, "filings": {"recent": recent, "files": files}},
        )


def _dump(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")))


def land_all(raw_dir: Path = config.RAW_DIR / "sec", out_dir: Path = config.PARQUET_DIR) -> dict:
    facts = land_facts(raw_dir, out_dir / "sec_facts.parquet", config.SEEDS_DIR / "concept_map.csv")
    filings, companies = land_filings(
        raw_dir, out_dir / "sec_filings.parquet", out_dir / "sec_companies.parquet"
    )
    return {"sec_facts": facts, "sec_filings": filings, "sec_companies": companies}
