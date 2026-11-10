"""Command-line entry points for ingestion, landing, fixtures and the calendar seed."""

import logging
from typing import Annotated

import pandas as pd
import typer
from dotenv import load_dotenv

from pitwh import calendar, config, prices, sec, universe

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


@app.command("land-fixtures")
def land_fixtures() -> None:
    """Land the committed fixtures into PARQUET_DIR so dbt runs offline (CI)."""
    counts = sec.land_all(raw_dir=config.FIXTURES_DIR / "sec", out_dir=config.parquet_dir())
    for table, n in counts.items():
        typer.echo(f"{table}: {n} rows")


@app.command("build-universe")
def build_universe() -> None:
    """Sample the S&P 500 history, resolve every ticker interval to a CIK, write Parquet."""
    pool = universe.in_window(
        universe.membership_intervals(universe.load_snapshots(universe.fetch_snapshots()))
    )
    resolver = universe.Resolver(sec.SecClient.from_env(), prices.TiingoClient.from_env())
    try:
        members = universe.select_universe(pool, resolver.resolve, resolver.same_company)
    except universe.UnresolvedTickers as exc:
        typer.echo(f"{exc}\nAdd verified rows to {universe.OVERRIDES_PATH} and rerun.", err=True)
        raise typer.Exit(1) from exc
    members["resolution"] = [
        resolver.method.get((t, s), "unknown")
        for t, s in zip(members.ticker, members.start_date, strict=True)
    ]
    supported = prices.supported_tickers(config.RAW_DIR / "tiingo")
    securities = universe.securities_table(members, resolver, supported)

    config.PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    members.to_parquet(config.PARQUET_DIR / "universe_membership.parquet", index=False)
    securities.to_parquet(config.PARQUET_DIR / "universe_securities.parquet", index=False)
    typer.echo(
        f"securities: {len(securities)}, departed: {int(securities.is_departed.sum())}, "
        f"without Tiingo coverage: {int(securities.price_symbol.isna().sum())}"
    )
    typer.echo(members.resolution.value_counts().to_string())


@app.command("ingest-prices")
def ingest_prices(
    refresh: Annotated[bool, typer.Option(help="Re-download even if cached")] = False,
) -> None:
    """Fetch Tiingo daily prices for every sampled security with coverage, then land Parquet."""
    securities = pd.read_parquet(config.PARQUET_DIR / "universe_securities.parquet")
    symbols = sorted(securities.price_symbol.dropna().unique())
    missing = prices.ingest_prices(
        prices.TiingoClient.from_env(), symbols, config.RAW_DIR / "tiingo", refresh
    )
    typer.echo(f"fetched {len(symbols) - len(missing)} of {len(symbols)}; missing: {missing}")
    typer.echo(f"prices_daily: {prices.land_all()} rows")


@app.command("calendar")
def write_calendar() -> None:
    """Write dbt/seeds/trading_calendar.csv from exchange_calendars (XNYS)."""
    n = calendar.write_calendar_seed()
    typer.echo(f"trading_calendar: {n} sessions")
