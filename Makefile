.PHONY: setup ingest build build-fixtures test lint bench all clean

export DUCKDB_PATH ?= $(CURDIR)/data/pitwh.duckdb
export PARQUET_DIR ?= $(CURDIR)/data/parquet
DBT = uv run dbt --no-use-colors
DBT_ARGS = --project-dir dbt --profiles-dir dbt
# Offline mode builds from committed fixtures in its own folder so it never
# overwrites the real landing tables or database.
FIXTURE_ENV = DUCKDB_PATH="$(CURDIR)/data/fixtures/pitwh.duckdb" PARQUET_DIR="$(CURDIR)/data/fixtures/parquet"
# The five-company fixture has one departed security (TWTR), not 30.
FIXTURE_VARS = --vars '{min_departed_securities: 1}'

setup:
	uv sync --locked
	mkdir -p data/raw data/parquet

# Needs SEC_USER_AGENT and TIINGO_API_KEY in .env. Downloads are cached in
# data/raw, so a rerun only fetches what is missing. The Tiingo starter plan
# allows 50 requests an hour, so a first full price download takes ~4 hours.
ingest: setup
	uv run pitwh build-universe
	uv run pitwh ingest-prices
	uv run pitwh ingest-sec --sample

build: setup
	$(DBT) seed --full-refresh $(DBT_ARGS)
	$(DBT) build $(DBT_ARGS)

build-fixtures: setup
	mkdir -p data/fixtures
	$(FIXTURE_ENV) uv run pitwh land-fixtures
	$(FIXTURE_ENV) $(DBT) seed --full-refresh $(DBT_ARGS)
	$(FIXTURE_ENV) $(DBT) build $(DBT_ARGS) $(FIXTURE_VARS)

lint:
	uv run ruff check .

test: lint
	uv run pytest

# Rebuilds the database from scratch (the build is one of the timings), then
# rewrites bench/results/latest.json and the README benchmark block.
bench: setup
	uv run python bench/run_benchmarks.py

all: ingest build test bench

clean:
	$(DBT) clean $(DBT_ARGS)
	rm -f $(DUCKDB_PATH)
