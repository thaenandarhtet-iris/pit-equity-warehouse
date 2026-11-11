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

## 2026-11-10: Tiingo serves delisted names, but only the current holder of a reused ticker
- **Decision:** pick each security's price symbol by checking the row Tiingo actually serves against the membership window (up to the window end for current members); securities with no covering symbol are reported, not dropped silently. The served row is the one with the latest `endDate` (latest `startDate` on a tie).
- **Correction (same day):** the first version used the latest `startDate`. That holds for DOW but not when a renamed company's history starts before the old holder's: COR has CoreSite (2010-2021) and Cencora (from 1995, ABC's history). The old rule marked Cencora, Healthpeak (DOC), DuPont (DD) and EchoStar unpriced. It also checked current members up to today instead of the window end, which marked Kenvue (prices end 2026-10-30) unpriced.
- **Evidence:** TWTR (ended 2022-10-28) and CELG (ended 2019-11-22) return full histories on the free plan. `supported_tickers.csv` has two DOW rows (Dow Chemical 1972-2017, Dow Inc 2019-), and a 2016 request for DOW returns `[]`. Renamed companies keep their whole history under the new ticker (META from 2012; FB is now an unrelated ETF).

## 2026-11-10: Sample by CIK: 30 departed first, then 170 from the whole pool
- **Decision:** seeded shuffle of departed tickers until 30 departed securities are in, then a seeded shuffle of all in-window tickers until 200 securities. A security is a CIK; it keeps every ticker it traded under.
- **Alternatives:** 170 current members plus exactly 30 departed.
- **Why:** 276 of 771 in-window tickers (36%) left the index; drawing from the whole pool keeps the sample's departed share close to reality, which is the point of a survivorship-bias-free universe.
- **Renames are linked both ways (fix, same day):** the first version only followed a same-day handoff backward (from a ticker to the one it replaced) or to the company's current ticker. A rename into a ticker that later left the index was missed, which ended L Brands at LB (2021) instead of BBWI (2024) and Paramount at VIAC (2022) instead of PARA (2025).

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

## 2026-11-10: TTM requires four consecutive known quarters
- **Decision:** `revenue_ttm` and `net_income_ttm` are null unless the four latest quarters known at `t` are consecutive (each starts the day after the previous ends).
- **Why:** summing non-adjacent quarters would mix fiscal years silently; a null is countable.

## 2026-11-10: CI fixtures for prices and universe use the same five companies
- **Decision:** trimmed real Tiingo responses and real membership intervals for AAPL, MSFT, NVDA, KHC and TWTR.
- **Why:** one slice runs through every layer offline, and TWTR exercises the delisted path end to end.

## 2026-11-10: Shares outstanding from the cover page
- **Decision:** market cap uses `dei:EntityCommonStockSharesOutstanding` as of its own date, per SPEC 6.2.
- **Limitation:** multi-class filers report one count per class; only the mapped value is used, so market cap can be understated for them.

## 2026-11-10: Availability rule: first session opening strictly after acceptance
- **Decision:** `available_ts` is the SEC `acceptanceDateTime` (UTC). `available_date` is the first XNYS session whose open is strictly after `available_ts`, found with `ASOF JOIN ... on accepted < market_open`.
- **Alternatives:** the filing date (a calendar date, no time, so an after-close filing would look tradeable that day); the next calendar day (wrong across weekends and holidays).
- **Why:** a filing accepted at 16:05 ET is unknown at that day's close, so a strategy trading on closes can't use it until the next session. Strictly after also handles a filing accepted at exactly 09:30:00 ET: it's not tradeable at that open. Covered by one dbt unit test with 7 cases: after the close, before the open, Friday after the close, a half day before a holiday, exactly at the open, either side of the switch to daylight time, and before the calendar starts.

## 2026-11-10: Derived quarters use the prior cumulative as known at the later filing
- **Decision:** a missing quarter is cumulative minus the previous cumulative (Q4 = FY - 9M). The previous value is the latest version accepted no later than the later filing (ASOF). If none exists yet, the first version is used. The derived version is available at the later of its two inputs. A directly reported quarter known no later replaces the derived one. EPS is never derived.
- **Alternatives:** subtract the latest restated prior value (uses information from the future); derive EPS too.
- **Why:** this keeps each derived value something an analyst could have computed on that day. EPS isn't additive because share counts change between quarters.

## 2026-11-10: Every filing is a version; restatement means a different value from the first
- **Decision:** `int_fundamentals__versions` keeps every filing's value for each (company, metric, period). `is_restatement` is true when the value differs from the first version by more than 1e-6 relative.
- **Why:** repeats of the same number in later comparatives are not restatements, and floating-point rounding shouldn't create false ones. KHC Q1 2017 net income: 893M first (2017-05-05), restated to 883M (2019-06-10), and that is the only flagged version.

## 2026-11-10: Snapshot events in two steps
- **Decision:** on each date a version becomes available, take (1) the latest period with any version known by then, as a running max, then (2) the latest version of that period accepted before that session's open.
- **Alternatives:** "most recently filed value", which is what a naive join does.
- **Why:** a 10-K re-reports older periods as comparatives; the naive rule then jumps back to an old quarter. On the fixtures the naive rule goes backward at least once and the two-step rule never does (`assert_snapshot_never_goes_backward` plus the pytest end-to-end check).

## 2026-11-10: Daily total return: `(close + div) * split / prev_close - 1`
- **Decision:** `ret_t = (close_t + div_cash_t) * split_factor_t / close_{t-1} - 1`, using raw vendor fields only.
- **Alternatives:** SPEC 6.6 as written, `(close_t * split_factor_t + div_t) / close_{t-1} - 1`.
- **Why:** Tiingo quotes `divCash` per share as of that day, after any split that day, so the dividend must be scaled by the split too. The two only differ when a split and a dividend fall on the same day.
- **Confirmed (2026-11-11):** on AAPL 2020-08-31 (4:1) and NVDA 2024-06-10 (10:1), multiplying the day's close by `splitFactor` matches the vendor's `adjClose` return to about 1e-13, so `splitFactor` is applied on the ex-date. The downloaded data has three days with a split factor and a dividend together, and on all three our formula matches the vendor exactly while SPEC's does not:

| day | ours | SPEC's literal formula | vendor |
|---|---|---|---|
| J 2025-05-16 | 2.3206% | 2.3104% | 2.3206% |
| DD 2019-06-03 (1:3 reverse split, Corteva spin-off) | 12.5707% | 71.4823% | 12.5707% |
| JEF 2019-09-27 | 3.9482% | 3.5135% | 3.9482% |

## 2026-11-10: Reconcile daily, not cumulatively, at 1e-4
- **Decision:** compare each day's return with the ratio of Tiingo's consecutive `adjClose` values. A day off by more than 1e-4 fails the test, and every mismatch is kept in a model the README counts.
- **Alternatives:** compound over the whole history and compare at the end.
- **Why:** over 11 years compounding adds up Tiingo's rounding into false failures and hides which day is wrong. Daily comparison names the day.
- **Result on the CI fixtures (2026-11-11):** 13,856 daily returns for the five test companies, largest gap from the vendor 2e-10. **Test the test:** raising one AAPL close (2021-03-01) by 1% in a scratch copy makes the test fail on exactly two rows, that day (+1.05%) and the next (-0.97%), and stores both.
- **Result on all real prices (2026-11-11):** 478,371 daily returns. The first run found 55 mismatches, 54 of them DD: old DuPont and DuPont de Nemours share Tiingo's DD series, and `fct_prices_daily` took the previous close per symbol, so each DD day was paired with its own duplicate. Fixed by taking it per security (unit-tested). After the fix one mismatch remains: AT&T (T) 2026-10-09, ours -9.70%, vendor -10.80%. Tiingo's raw fields report a 0.2775 dividend that day, but its adjusted-to-raw ratio barely moves across the ex-date (0.98764 to 0.98781), so the vendor's adjusted series has not absorbed that dividend. Every other return matches within 2.1e-10.

## 2026-11-10: `dim_security` is SCD2 on CIK, changing on ticker or membership
- **Decision:** one row per CIK for each interval where its ticker and S&P 500 membership are unchanged, with `valid_from`/`valid_to`. A rename (FB to META) or leaving the index starts a new row.
- **Why:** the point-in-time join needs to know which ticker and membership applied on a given date.
- **Detail:** a CIK can have two share classes in the index at once (GOOG and GOOGL), so each row holds a sorted `tickers` list rather than one ticker. Rows outside the index have `is_member = false` and null tickers: tickers are only tracked while a member, and guessing one would be invented data. `assert_dim_security_intervals_tile` checks that the rows have no gaps, no overlaps and exactly one open row; it was itself checked against an overlap, a gap, two open rows and a closed last row.

## 2026-11-10: The naive model keys on period_end and takes the latest version
- **Decision:** `fct_features_daily_naive` treats each value as known on its fiscal `period_end` and always uses the most recently filed version. Everything else (grid, TTM rule, ratios) is shared with the PIT model through the `daily_features` macro, so the two differ only in the leak.
- **Why:** that's the usual shortcut, and it leaks twice: the filing lag, and restated values back-filled to the original date. `assert_naive_model_leaks` fails if the look-ahead check finds nothing in it, which is what makes `assert_no_lookahead` passing meaningful.

## 2026-11-10: Debt-to-equity is not nulled for negative equity
- **Decision:** `debt_to_equity = total_liabilities / stockholders_equity`, null only when equity is zero. P/E and P/B are null when the denominator is not positive, as SPEC 6.7 says.
- **Why:** SPEC states the null rule for P/E and P/B but not D/E. A negative D/E is a real signal (negative book equity) rather than a divide-by-zero, so it is kept; users can filter it.

## 2026-11-10: 50 ticker intervals resolved by hand; Signature Bank kept without an SEC CIK
- **Decision:** 49 intervals the automatic resolver couldn't match are in `ticker_cik_overrides.csv`, each checked against EDGAR submissions (periodic filings inside the interval, plus the SEC current or former name and, for most, filenames that cite the ticker). Signature Bank (SBNY) has ID -1: it filed with the FDIC, not the SEC, so it stays in the universe with membership and prices but no fundamentals.
- **Why they failed automatically:** most are reused tickers. Tiingo's metadata names the ticker's current holder (FB is now an ETF, GPS another company), so the name search finds the wrong company or nothing.
- **Two intervals span two filers:** MYL is assigned to Mylan N.V. (1623613) from its first filing on 2015-02-27; Jan-Feb 2015 belonged to Mylan Inc (69499). BHGE is assigned to the listed Baker Hughes parent (1701605), which also holds BKR; 2015 to mid-2017 belonged to Baker Hughes Inc (808362, now a subsidiary LLC). Both gaps have null fundamentals. *Superseded the same day by the filer-change entry below: MYL now chains Mylan Inc into Mylan N.V., and Baker Hughes Inc is its own departed security.*
- **Alternatives for SBNY:** drop non-SEC filers and draw a replacement. Rejected by the owner: a failed bank is exactly what survivorship bias hides.

## 2026-11-10: A security can change SEC filer; filings count only while their filer reports for it
- **Decision:** a security is keyed on `security_id` (its latest CIK, or a negative ID for a non-SEC filer). `universe_filers` lists each filer CIK with the acceptance dates it reports for the security, `[valid_from, valid_to)`. `int_filings__availability` assigns each filing to a security through that table, so a reorganized company's fundamentals run across the handoff, and a predecessor that keeps filing as a subsidiary afterwards (Xerox Corp, Mylan Inc, EIDP) stops counting at the handoff. Handoffs are hand-verified in `filer_history.csv` from EDGAR: the successor's 8-K12B/8-K12G3 or the predecessor's 25-NSE/15-12B.
- **Reorganizations, one security:** AVGO (Avago, then Broadcom Ltd 2016-02-02, then Broadcom Inc 2018-04-04), XRX (2019-07-31), BG (2023-11-01), BLK (2024-10-01), XOM (2026-07-01), MYL (2015-02-27).
- **Mergers, separate securities:** the interval is split and the predecessor becomes its own departed security: old DuPont (DD until 2017-09-01), Baker Hughes Inc (BHGE until 2017-07-03), 21st Century Fox (FOXA and FOX until 2019-03-20). The sample is 200 drawn securities, 203 after these splits.
- **Why:** the resolver had mapped XOM to ExxonMobil Holdings, whose first 10-Q is 2026-07-01, which would leave Exxon with no fundamentals for 2015-2026. `build-universe` now stops if any filer starts reporting more than 120 days into the in-window part of its interval, so new cases are caught.
- **Alternatives:** one CIK per security, chosen by which filed most of the window (loses fundamentals on one side of each handoff); leave the 9 as a README limitation.

## 2026-11-10: 22 departed securities have no prices; accepted as a limitation
- **Decision:** the 22 departed securities Tiingo can't serve (their tickers now belong to other companies, e.g. TE, HOT, PARA) keep their membership and fundamentals with null returns. No second price vendor.
- **Why:** a second vendor is a new dependency for 22 names, and SPEC says to add one only when it's really needed. The README states the count and the bias: failed and acquired names stay in the universe but are under-represented in any return statistic.

## 2026-11-10: The sample is 203 securities
- **Decision:** keep the 200 seeded draws plus the 3 merged-away predecessors split out of them (old DuPont, Baker Hughes Inc, 21st Century Fox), rather than re-drawing to exactly 200.
- **Why:** re-drawing would change the seeded sample to hit a round number; the split-out securities are real former index members.

## 2026-11-11: Reviewed vendor-side reconciliation exceptions live in a seed
- **Decision:** `reconciliation_exceptions.csv` lists (security, day) mismatches traced to the vendor, each with its evidence. `assert_returns_reconcile_to_vendor` skips listed rows only, so any new mismatch still fails the build. The README shows the count. One row today: AT&T 2026-10-09.
- **Alternatives:** widen the tolerance; make the test a warning; leave the build failing.
- **Why:** a wider tolerance or a warning would hide the next real bug (the DD shared-symbol bug was 55 rows), and a build that always fails stops being a gate.

## 2026-11-11: A quarter tagged in two contexts in one filing keeps the full span
- **Decision:** `int_facts__mapped` keeps one fact per (security, metric, duration class, period end, filing): the highest-priority tag, then the longest span.
- **Alternatives:** key on period start as before; keep the most precise value.
- **Why:** the full build found 4 duplicate versions. Companyfacts drops XBRL dimensions, so one filing can tag the same quarter twice with shifted starts. J.B. Hunt's 10-Q of 2014-07-29 gives Q2 2013 revenue as 1,382,858,000 (2013-04-01 to 06-30) and a rounded 1,383,000,000 (from 04-04). Nordstrom and Williams-Sonoma repeat equal values with starts a day or two apart. The full span is the fiscal period the filing reports. Unit-tested on the J.B. Hunt case.

## 2026-11-11: Benchmark subsets are prefixes of one seeded order
- **Decision:** the 50/100/200-security subsets are prefixes of the 203 security IDs, sorted and then shuffled with `UNIVERSE_SEED`, so each subset contains the smaller ones.
- **Alternatives:** independent draws per size; the sampler's own draw order. The sampler doesn't record order, and the 3 split-out predecessors were never drawn.
- **Why:** with nested subsets, timing differences come from size, not from which companies were picked.

## 2026-11-11: Leakage is reported two ways
- **Decision:** the headline follows SPEC: a naive row leaks if its value differs from PIT *or* it cites a filing not yet public. The README also shows the stricter share where the value itself differs.
- **Why:** the naive model takes the latest version of each period, which is often next year's 10-K comparative repeating an unchanged number. That row cites the future without changing the value. Showing both stops the headline from being read as inflated.

## 2026-11-11: The correlated subquery is decorrelated by DuckDB
- **Finding:** the correlated subquery takes 4-6x as long as `ASOF JOIN`, not orders of magnitude. DuckDB rewrites correlated subqueries into joins, so it doesn't run per row. The window strategy is within about 30% of `ASOF JOIN` either way, and slightly faster at 200 securities in the first full run. The README reports the measured numbers as they are. `ASOF JOIN` stays the primary path because it is the shortest correct statement of the rule, not because it wins every size.
