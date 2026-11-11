"""Build the warehouse from the committed fixtures and check real outcomes."""

from datetime import date

import duckdb
import pytest
from dbt.cli.main import dbtRunner

from pitwh import config
from pitwh.fixtures import land_fixtures

AAPL, KHC = 320193, 1637459


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory, monkeypatch_module):
    root = tmp_path_factory.mktemp("warehouse")
    parquet = root / "parquet"
    parquet.mkdir()
    land_fixtures(parquet)
    monkeypatch_module.setenv("DUCKDB_PATH", str(root / "pitwh.duckdb"))
    monkeypatch_module.setenv("PARQUET_DIR", str(parquet))
    args = ["--project-dir", str(config.DBT_DIR), "--profiles-dir", str(config.DBT_DIR)]
    for command in (["seed", "--full-refresh"], ["run"]):
        result = dbtRunner().invoke([*command, *args])
        assert result.success, result.exception
    # dbt-duckdb keeps its in-process connection open, so match its (read-write) config.
    con = duckdb.connect(str(root / "pitwh.duckdb"))
    yield con
    con.close()


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


def test_apple_q4_is_derived_from_the_10k_and_matches_reported(warehouse):
    # Apple files no Q4 10-Q; fiscal Q4 2023 revenue was $89.498B and net income
    # $22.956B. The 10-K was accepted after the close on 2023-11-02.
    rows = warehouse.execute(
        """
        select metric, value, available_date
        from int_facts__discrete_quarters
        where security_id = ? and period_end = '2023-09-30' and is_derived
        qualify row_number() over (partition by metric order by available_ts) = 1
        order by metric
        """,
        [AAPL],
    ).fetchall()
    assert rows == [
        ("net_income", 22_956_000_000.0, date(2023, 11, 3)),
        ("revenue", 89_498_000_000.0, date(2023, 11, 3)),
    ]


def test_kraft_heinz_2017_restatement_is_flagged(warehouse):
    # KHC reported Q1 2017 net income of $893M in May 2017; its delayed 10-K of
    # June 2019 restated it to $883M. Earlier repeats of $893M are not restatements.
    versions = warehouse.execute(
        """
        select value, is_restatement, available_date
        from int_fundamentals__versions
        where security_id = ? and metric = 'net_income' and period_end = '2017-04-01'
        order by version_number
        """,
        [KHC],
    ).fetchall()
    assert versions[0] == (893_000_000.0, False, date(2017, 5, 5))
    assert [v for v in versions if v[1]] == [(883_000_000.0, True, date(2019, 6, 10))]


def test_latest_filed_lookup_would_go_backward_but_snapshot_does_not(warehouse):
    # The naive rule (take the most recently accepted version, whatever its
    # period) must regress on this real data, or the two-step rule is untested.
    naive_regressions = warehouse.execute(
        """
        with latest as (
            select
                security_id, metric, available_date,
                arg_max(period_end, available_ts) as period_end
            from int_fundamentals__versions
            group by all
        )
        select count(*) from (
            select period_end < lag(period_end) over (
                partition by security_id, metric order by available_date) as backward
            from latest
        ) where backward
        """
    ).fetchone()[0]
    pit_regressions = warehouse.execute(
        """
        select count(*) from (
            select period_end < lag(period_end) over (
                partition by security_id, metric order by event_date) as backward
            from int_fundamentals__snapshot_events
        ) where backward
        """
    ).fetchone()[0]
    assert naive_regressions > 0
    assert pit_regressions == 0


def test_apple_ttm_after_fy2023_10k_equals_reported_fiscal_year(warehouse):
    # Apple's FY2023 (ended 2023-09-30) revenue was $383.285B and net income
    # $96.995B. TTM known the session after the 10-K must equal those totals.
    rows = warehouse.execute(
        """
        select metric, value
        from int_fundamentals__ttm_events
        where security_id = ? and event_date = '2023-11-03'
        order by metric
        """,
        [AAPL],
    ).fetchall()
    assert rows == [("net_income_ttm", 96_995_000_000.0), ("revenue_ttm", 383_285_000_000.0)]


def test_split_day_return_is_not_read_as_a_crash(warehouse):
    # AAPL split 4:1 on 2020-08-31 (the fixture prices are synthetic, the split
    # date and factor are real). The raw close falls to about a quarter, but the
    # total return that day must be an ordinary daily move.
    (raw_ratio, ret) = warehouse.execute(
        """
        select close / lag(close) over (order by trade_date), daily_return
        from fct_prices_daily where security_id = ?
        qualify trade_date = ?
        """,
        [AAPL, date(2020, 8, 31)],
    ).fetchone()
    assert raw_ratio < 0.3
    assert abs(ret) < 0.1
    assert ret == pytest.approx(raw_ratio * 4 - 1, abs=1e-12)
