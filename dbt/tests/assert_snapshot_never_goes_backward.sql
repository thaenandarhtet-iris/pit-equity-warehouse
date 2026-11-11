-- The point-in-time period for a (company, metric) must never move to an older
-- period as time passes, which is what 10-K comparatives would cause under a
-- plain "most recently filed fact" lookup.
select *
from (
    select
        security_id,
        metric,
        event_date,
        period_end,
        lag(period_end) over (partition by security_id, metric order by event_date) as previous_period_end
    from {{ ref('int_fundamentals__snapshot_events') }}
)
where period_end < previous_period_end
