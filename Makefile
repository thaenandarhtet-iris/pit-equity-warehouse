.PHONY: setup ingest build build-fixtures test lint bench all clean

export DUCKDB_PATH ?= $(CURDIR)/data/pitwh.duckdb
export PARQUET_DIR ?= $(CURDIR)/data/parquet
DBT = uv run dbt --no-use-colors
DBT_ARGS = --project-dir dbt --profiles-dir dbt
# Offline mode builds from committed fixtures in its own folder so it never
# overwrites the real landing tables or database.
FIXTURE_ENV = DUCKDB_PATH="$(CURDIR)/data/fixtures/pitwh.duckdb" PARQUET_DIR="$(CURDIR)/data/fixtures/parquet"

setup:
	uv sync --locked
	mkdir -p data/raw data/parquet

ingest:
	@echo "ingest is implemented in Phases 1-2" >&2; exit 1

build: setup
	$(DBT) seed $(DBT_ARGS)
	$(DBT) build $(DBT_ARGS)

build-fixtures: setup
	mkdir -p data/fixtures
	$(FIXTURE_ENV) uv run pitwh land-fixtures
	$(FIXTURE_ENV) $(DBT) seed $(DBT_ARGS)
	$(FIXTURE_ENV) $(DBT) build $(DBT_ARGS)

lint:
	uv run ruff check .

test: lint
	uv run pytest

bench:
	@echo "bench is implemented in Phase 5" >&2; exit 1

all: ingest build test bench

clean:
	$(DBT) clean $(DBT_ARGS)
	rm -f $(DUCKDB_PATH)
