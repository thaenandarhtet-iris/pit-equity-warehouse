# Decisions

Short log of non-obvious choices. Newest at the bottom.

## 2026-11-10: Repo location
- **Decision:** the repo lives at `~/Desktop/PROJECTS 26/pit-equity-warehouse/`, not `projects 26/pit-equity-warehouse/` as SPEC.md says.
- **Why:** that's where the owner keeps the other portfolio projects. Nothing in the code depends on the absolute path (`config.REPO_ROOT` is derived from the package location).

## 2026-11-10: Python 3.12 pinned via `.python-version`
- **Decision:** `requires-python = ">=3.11"` per spec, local and CI interpreter pinned to 3.12.
- **Alternatives:** 3.13 (the system Python here).
- **Why:** dbt-core and exchange_calendars ship and test against 3.12 well before the newest minor; one pinned version keeps local and CI identical.

## 2026-11-10: Ruff rule set includes `BLE` and `B`
- **Decision:** lint with `E, F, W, I, B, UP, BLE, SIM`.
- **Why:** `BLE` (blind except) mechanically enforces the spec's "no `except Exception: pass`" rule instead of relying on review.

## 2026-11-10: dbt profile reads an absolute `DUCKDB_PATH`
- **Decision:** `profiles.yml` is project-local and reads `DUCKDB_PATH`; the Makefile and CI set it to an absolute path under `data/`.
- **Why:** dbt-duckdb resolves a relative path against the shell's cwd, so the same command run from the repo root and from `dbt/` would otherwise write two different databases.

## 2026-11-10: Unbuilt Makefile targets fail loudly
- **Decision:** `ingest` and `bench` exit 1 with a message until their phases land.
- **Why:** a no-op that exits 0 would make `make all` look green while doing nothing.

## 2026-11-10: No CLI module until Phase 1
- **Decision:** `cli.py` and the `pitwh` console script are deferred to Phase 1, when the first real command (`ingest-sec`) exists.
- **Why:** an empty Typer app is placeholder code with nothing to test.
