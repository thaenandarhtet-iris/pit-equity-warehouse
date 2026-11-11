from datetime import date

import duckdb
import pytest

from pitwh.bench import STRATEGIES, nested_subsets, replace_block, run_strategy


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute(
        """
        create table grid as
        select * from (values
            (date '2020-01-02', 1, 'revenue_ttm'),
            (date '2020-01-03', 1, 'revenue_ttm'),
            (date '2020-01-06', 1, 'revenue_ttm'),
            (date '2020-01-07', 1, 'revenue_ttm'),
            (date '2020-01-06', 2, 'revenue_ttm')
        ) as t(trade_date, security_id, metric)
        """
    )
    con.execute(
        """
        create table events as
        select * from (values
            (1, 'revenue_ttm', date '2020-01-03', 10.0, date '2020-01-03'),
            (1, 'revenue_ttm', date '2020-01-06', 11.0, date '2020-01-06'),
            (1, 'total_assets', date '2020-01-01', 99.0, date '2020-01-01')
        ) as t(security_id, metric, event_date, value, source_available_date)
        """
    )
    return con


EXPECTED = [
    (date(2020, 1, 2), 1, "revenue_ttm", None, None),
    (date(2020, 1, 3), 1, "revenue_ttm", 10.0, date(2020, 1, 3)),
    (date(2020, 1, 6), 1, "revenue_ttm", 11.0, date(2020, 1, 6)),
    (date(2020, 1, 6), 2, "revenue_ttm", None, None),
    (date(2020, 1, 7), 1, "revenue_ttm", 11.0, date(2020, 1, 6)),
]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_each_strategy_takes_the_latest_event_on_or_before_the_trade_date(con, strategy):
    run_strategy(con, strategy, "out")
    assert con.sql("select * from out order by all").fetchall() == EXPECTED


def test_subsets_are_nested_and_reproducible():
    ids = list(range(300, 503))
    subsets = nested_subsets(ids, [50, 100, 200], seed=7)
    assert [len(s) for s in subsets] == [50, 100, 200]
    assert set(subsets[0]) < set(subsets[1]) < set(subsets[2])
    assert nested_subsets(list(reversed(ids)), [50, 100, 200], seed=7) == subsets


def test_replace_block_rewrites_only_between_the_markers():
    readme = "intro\n<!-- BENCH:START -->\nold\n<!-- BENCH:END -->\noutro\n"
    assert replace_block(readme, "new table") == (
        "intro\n<!-- BENCH:START -->\nnew table\n<!-- BENCH:END -->\noutro\n"
    )
