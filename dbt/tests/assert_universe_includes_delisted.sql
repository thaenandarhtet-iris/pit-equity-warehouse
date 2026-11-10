-- The grid must contain at least min_departed_securities securities whose last
-- day in the index is before the end of the window. A universe of today's
-- members would return a row here and fail.
with last_day as (
    select security_id, max(trade_date) as last_trade_date
    from {{ ref('fct_universe_daily') }}
    group by all
)
select count(*) as departed
from last_day
where last_trade_date < (
    select max(trade_date) from {{ ref('fct_universe_daily') }}
)
having count(*) < {{ var('min_departed_securities') }}
