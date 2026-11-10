-- The point-in-time state of each (company, metric) on every date a new
-- version became available. Two steps:
--   1. the latest period with any version available by that date;
--   2. for that period, the most recently accepted version available by then.
-- Step 1 is why a 10-K's comparatives for older periods never pull the state
-- backward; step 2 is why a restatement of the current period does replace it.
with versions as (
    select * from {{ ref('int_fundamentals__versions') }}
),

per_date as (
    select cik, metric, available_date, max(period_end) as max_period_end
    from versions
    group by all
),

latest_period as (
    select
        p.cik,
        p.metric,
        p.available_date as event_date,
        max(p.max_period_end) over (
            partition by p.cik, p.metric
            order by p.available_date
            rows between unbounded preceding and current row
        ) as period_end,
        -- available_date <= event_date exactly when available_ts is before that
        -- session's open, which orders same-day versions by acceptance time.
        s.market_open_utc as cutoff_ts
    from per_date as p
    inner join {{ ref('stg_calendar__sessions') }} as s
        on p.available_date = s.session_date
)

select
    l.cik,
    l.metric,
    l.event_date,
    v.period_start,
    l.period_end,
    v.value,
    v.accession_number,
    v.available_ts,
    v.available_date,
    v.is_derived,
    v.is_restatement
from latest_period as l
asof inner join versions as v
    on l.cik = v.cik
    and l.metric = v.metric
    and l.period_end = v.period_end
    and l.cutoff_ts > v.available_ts
