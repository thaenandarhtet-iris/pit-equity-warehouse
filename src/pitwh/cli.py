"""Command-line entry points for ingestion, landing, fixtures and the calendar seed."""

import logging
from typing import Annotated

import typer
from dotenv import load_dotenv

from pitwh import calendar, config, sec

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    load_dotenv(config.REPO_ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@app.command("ingest-sec")
def ingest_sec(
    cik: Annotated[list[int] | None, typer.Option(help="CIK to fetch; repeatable")] = None,
    refresh: Annotated[bool, typer.Option(help="Re-download even if cached")] = False,
) -> None:
    """Fetch tickers, submissions and companyfacts into data/raw/sec, then land Parquet."""
    raw_dir = config.RAW_DIR / "sec"
    client = sec.SecClient.from_env()
    sec.ingest_company_tickers(client, raw_dir, refresh)
    ciks = cik or list(config.SEC_TEST_CIKS.values())
    for c in ciks:
        sec.ingest_company(client, c, raw_dir, refresh)
    typer.echo(f"fetched {len(ciks)} companies")
    land_sec()


@app.command("land-sec")
def land_sec() -> None:
    """Rebuild the SEC Parquet landing tables from the raw cache only."""
    counts = sec.land_all()
    for table, n in counts.items():
        typer.echo(f"{table}: {n} rows")


@app.command("make-fixtures")
def make_fixtures() -> None:
    """Trim the raw SEC cache into tests/fixtures/sec for offline tests and CI."""
    out = config.FIXTURES_DIR / "sec"
    sec.trim_fixtures(config.RAW_DIR / "sec", out, config.SEEDS_DIR / "concept_map.csv")
    typer.echo(f"wrote fixtures to {out}")


@app.command("calendar")
def write_calendar() -> None:
    """Write dbt/seeds/trading_calendar.csv from exchange_calendars (XNYS)."""
    n = calendar.write_calendar_seed()
    typer.echo(f"trading_calendar: {n} sessions")
