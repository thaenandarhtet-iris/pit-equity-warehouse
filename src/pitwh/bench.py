"""As-of join strategies and helpers for bench/run_benchmarks.py.

Each strategy reads tables `grid` (trade_date, security_id, metric) and
`events` (security_id, metric, event_date, value, source_available_date) and
writes the same table: every grid row with the latest event on or before its
trade date, or nulls when there is none.
"""

import random
import re
from collections.abc import Sequence

import duckdb

ASOF_SQL = """
select g.trade_date, g.security_id, g.metric, e.value, e.source_available_date
from grid as g
asof left join events as e
    on g.security_id = e.security_id
    and g.metric = e.metric
    and g.trade_date >= e.event_date
"""

# Correlated subquery: for each grid row, sort its company's earlier events and
# take the first. A struct keeps value and date from the same event.
SUBQUERY_SQL = """
select
    trade_date, security_id, metric,
    hit.value as value,
    hit.source_available_date as source_available_date
from (
    select
        g.*,
        (
            select {'value': e.value, 'source_available_date': e.source_available_date}
            from events as e
            where e.security_id = g.security_id
                and e.metric = g.metric
                and e.event_date <= g.trade_date
            order by e.event_date desc
            limit 1
        ) as hit
    from grid as g
)
"""

# Window: interleave events and grid rows in date order (an event sorts before
# a grid row on the same day, since it is known by then) and carry the last
# event forward with LAST_VALUE ... IGNORE NULLS.
WINDOW_SQL = """
select trade_date, security_id, metric, hit.value as value,
    hit.source_available_date as source_available_date
from (
    select
        d as trade_date, security_id, metric, is_grid,
        last_value(ev ignore nulls) over (
            partition by security_id, metric
            order by d, is_grid
            rows between unbounded preceding and current row
        ) as hit
    from (
        select event_date as d, security_id, metric, false as is_grid,
            {'value': value, 'source_available_date': source_available_date} as ev
        from events
        union all
        select trade_date, security_id, metric, true, null
        from grid
    )
)
where is_grid
"""

STRATEGIES = {
    "asof_join": ASOF_SQL,
    "correlated_subquery": SUBQUERY_SQL,
    "window_last_value": WINDOW_SQL,
}


def run_strategy(con: duckdb.DuckDBPyConnection, strategy: str, out: str) -> None:
    """Materialize the strategy's result, so timing covers the whole join."""
    con.execute(f"create or replace temp table {out} as {STRATEGIES[strategy]}")


def nested_subsets(ids: Sequence[int], sizes: Sequence[int], seed: int) -> list[list[int]]:
    """Prefixes of one seeded shuffle, so each subset contains the smaller ones."""
    order = sorted(ids)
    random.Random(seed).shuffle(order)
    return [order[:n] for n in sizes]


BLOCK = re.compile(r"(<!-- BENCH:START -->\n).*?(<!-- BENCH:END -->)", re.DOTALL)


def replace_block(readme: str, table: str) -> str:
    if not BLOCK.search(readme):
        raise ValueError("README has no BENCH:START/BENCH:END block")
    return BLOCK.sub(lambda m: f"{m[1]}{table}\n{m[2]}", readme)
