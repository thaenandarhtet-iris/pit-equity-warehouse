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

# Changing the seed or sizes changes which securities are sampled, so every
# downstream number in the README changes with it.
UNIVERSE_SEED = 20261110
UNIVERSE_SIZE = 200
MIN_DEPARTED_SECURITIES = 30
