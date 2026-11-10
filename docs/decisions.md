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

## 2026-11-10: `acceptanceDateTime` is true UTC
- **Decision:** parse `acceptanceDateTime` as UTC with no shift.
- **Alternatives:** treat it as Eastern time mislabeled with a `Z`.
- **Why:** compared 8 filings against the "Accepted" time on their EDGAR index pages (Eastern time). The gap is 4 h during daylight saving and 5 h outside it, which is what true UTC produces; mislabeled Eastern would show a 0 h gap.

| accession | json (`Z`) | index page (ET) | gap |
|---|---|---|---|
| 0001564590-16-017462 (TWTR 10-Q) | 2016-05-03 20:32:14 | 2016-05-03 16:32:14 | 4 h |
| 0001564590-17-007547 (MSFT 10-Q) | 2017-04-27 20:16:04 | 2017-04-27 16:16:04 | 4 h |
| 0001637459-18-000124 (KHC 10-Q) | 2018-11-02 15:37:21 | 2018-11-02 11:37:21 | 4 h (DST ended Nov 4) |
| 0001637459-19-000072 (KHC 10-Q) | 2019-08-13 10:06:38 | 2019-08-13 06:06:38 | 4 h |
| 0001637459-22-000159 (KHC 10-Q) | 2022-07-28 11:43:03 | 2022-07-28 07:43:03 | 4 h |
| 0001045810-24-000316 (NVDA 10-Q) | 2024-11-20 21:31:22 | 2024-11-20 16:31:22 | 5 h |
| 0001637459-21-000009 (KHC 10-K) | 2021-02-17 12:32:36 | 2021-02-17 07:32:36 | 5 h |
| 0001637459-25-000011 (KHC 10-K) | 2025-02-13 12:42:01 | 2025-02-13 07:42:01 | 5 h |

## 2026-11-10: Phase 1 test companies
- **Decision:** AAPL (FY ends Sep), MSFT (Jun), NVDA (Jan), KHC (2019 restatement of 2015-2017), TWTR (taken private 2022), keyed on CIK in `config.SEC_TEST_CIKS`.
- **Why:** covers non-December fiscal years, a real restatement (KHC Q1 2017 net income appears as both 883M and 893M), and a delisted former S&P 500 member. TWTR is absent from `company_tickers.json`, which confirms delisted names must be keyed on CIK, not looked up by current ticker.

## 2026-11-10: Fixtures are trimmed real responses in the raw cache layout
- **Decision:** `pitwh make-fixtures` keeps only concept-map tags in companyfacts and only the filings those facts cite in submissions (including overflow files), written under `tests/fixtures/sec/` with the same layout as `data/raw/sec/`.
- **Alternatives:** hand-written synthetic JSON; committing the full responses (~21 MB).
- **Why:** the landing code runs unchanged on fixtures, so CI exercises the real parser on real shapes; the trimmed set is under 1 MB.
