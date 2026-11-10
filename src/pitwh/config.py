"""Project-wide paths and sample parameters."""

from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"
DBT_DIR = REPO_ROOT / "dbt"
SEEDS_DIR = DBT_DIR / "seeds"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

START_DATE = date(2015, 1, 1)

# Phase 1 test companies, keyed on CIK because delisted names drop out of
# company_tickers.json. Chosen to cover non-December fiscal years (AAPL Sep,
# MSFT Jun, NVDA Jan), a restatement (KHC, 2019 restatement of 2015-2017),
# and a delisted former member (TWTR, taken private 2022).
SEC_TEST_CIKS = {
    "AAPL": 320193,
    "MSFT": 789019,
    "NVDA": 1045810,
    "KHC": 1637459,
    "TWTR": 1418091,
}

# Changing the seed or sizes changes which securities are sampled, so every
# downstream number in the README changes with it.
UNIVERSE_SEED = 20261110
UNIVERSE_SIZE = 200
MIN_DEPARTED_SECURITIES = 30

# The calendar starts before START_DATE so filings accepted late in 2014 still
# map to a session, and runs past today so recent filings can roll forward.
CALENDAR_START = date(2014, 1, 1)
CALENDAR_END = date(2027, 6, 30)
