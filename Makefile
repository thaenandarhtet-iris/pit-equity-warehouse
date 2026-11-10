.PHONY: setup ingest build test lint bench all clean

export DUCKDB_PATH ?= $(CURDIR)/data/pitwh.duckdb
DBT = uv run dbt --no-use-colors
DBT_ARGS = --project-dir dbt --profiles-dir dbt

setup:
	uv sync --locked
	mkdir -p data/raw data/parquet

ingest:
	@echo "ingest is implemented in Phases 1-2" >&2; exit 1

build: setup
	$(DBT) seed $(DBT_ARGS)
	$(DBT) build $(DBT_ARGS)

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
