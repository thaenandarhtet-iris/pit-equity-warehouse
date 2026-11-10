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

## 2026-11-10: Tiingo Starter (free) plan, throttled to 45 requests/hour
- **Decision:** stay on the free plan; `TiingoClient` sends at most 45 requests/hour and passes the key in an `Authorization: Token` header.
- **Alternatives:** Power plan ($30/month, 10,000 requests/hour); the `token=` query parameter.
- **Why:** published Starter limits (tiingo.com/about/pricing, checked 2026-11-10) are 50 requests/hour, 1,000/day and 500 unique symbols/month, enough for ~200 symbols if fetched once and cached. Staying under 50 leaves room for a manual request. A query-string key would land in httpx's request logs.

## 2026-11-10: Tiingo serves delisted names, but only the newest holder of a reused ticker
- **Decision:** pick each security's price symbol by checking the row Tiingo actually serves (latest `startDate` in `supported_tickers.csv`) against the membership window; securities with no covering symbol are reported, not dropped silently.
- **Evidence:** TWTR (ended 2022-10-28) and CELG (ended 2019-11-22) return full histories on the free plan. `supported_tickers.csv` has two DOW rows (Dow Chemical 1972-2017, Dow Inc 2019-), and a 2016 request for DOW returns `[]`. Renamed companies keep their whole history under the new ticker (META from 2012; FB is now an unrelated ETF).

## 2026-11-10: Sample by CIK: 30 departed first, then 170 from the whole pool
- **Decision:** seeded shuffle of departed tickers until 30 departed securities are in, then a seeded shuffle of all in-window tickers until 200 securities. A security is a CIK; it keeps every ticker it traded under.
- **Alternatives:** 170 current members plus exactly 30 departed.
- **Why:** 276 of 771 in-window tickers (36%) left the index; drawing from the whole pool keeps the sample's departed share close to reality, which is the point of a survivorship-bias-free universe.

## 2026-11-10: A ticker-to-CIK match must be verified
- **Decision:** order is `ticker_cik_overrides.csv`, then the SEC's current ticker map, then the Tiingo company name searched on EDGAR. Every automatic match must have filed a 10-K/10-Q during the membership interval (plus 120 days). A closed interval matched through the current map also needs a filing whose filename starts with the old ticker (`fb-20211231.htm`), or a matching company name. Unresolved intervals stop the build and are listed for hand-checked overrides.
- **Why:** the current map silently mislabels reused tickers (DOW old vs new). Filenames separate renames from same-day index swaps: FB->META 29 of 30 periodic filings cite `fb-`, BK->BNY 23 of 46, while TWTR->ACGL and CBS->WRB cite 0. One-letter tickers need a separator after the ticker (`a201410-k.htm` is Arch Capital's, not Agilent's).

## 2026-11-10: Unpriceable securities stay in the universe
- **Decision:** a sampled security with no Tiingo coverage keeps its membership and fundamentals, has null returns, and is counted in the README limitations.
- **Alternatives:** drop it; replace it with the next draw.
- **Why:** both alternatives remove exactly the names survivorship bias hides.

## 2026-11-10: Universe window ends at the last membership snapshot
- **Decision:** `fct_universe_daily` stops at the last date in the S&P 500 history file (2026-08-18 in the pinned version), even though prices run later.
- **Why:** membership after the last snapshot is unknown; carrying it forward would assume no index changes since.

## 2026-11-10: Best XBRL tag is chosen per filing, not per period (deviates from SPEC 6.2)
- **Decision:** within each filing, a (company, metric, period) takes the highest-priority tag that filing used. Each filing is its own version.
- **Alternatives:** SPEC 6.2 as written: best tag per (company, metric, period) across all filings.
- **Why:** filers change tags over time and re-report old periods under the new tag (AAPL: `SalesRevenueNet` through 2018, then `RevenueFromContractWithCustomerExcludingAssessedTax` in comparatives). Choosing across all filings would discard the original version and date the period to a later filing, which breaks the point-in-time history.

## 2026-11-10: SQL logic is tested with dbt unit tests plus a pytest end-to-end build
- **Decision:** availability-rule and quarter-derivation edge cases are dbt unit tests (literal input rows into the real models); pytest runs `dbt build` on the committed fixtures and asserts real outcomes.
- **Alternatives:** SPEC 8.2's pytest-only wording, which would mean building Parquet inputs per edge case or reimplementing the SQL in Python.
- **Why:** the tests exercise the SQL that ships instead of a parallel implementation.
