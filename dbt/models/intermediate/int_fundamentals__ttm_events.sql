-- Trailing-twelve-month revenue and net income on every date a new quarter
-- version became available. Each of the four quarters uses its own latest
-- version known before that session's open, so a restatement of an older
-- quarter moves TTM only from the day it is filed. Null unless the four
-- latest known quarters are consecutive.
with quarters as (
    select security_id, metric, period_start, period_end, value, accession_number, available_ts, available_date
    from {{ ref('int_fundamentals__versions') }}
    where metric in ('revenue', 'net_income')
),
events as (
    select distinct q.security_id, q.metric, q.available_date as event_date, s.market_open_utc as cutoff_ts
    from quarters as q
    inner join {{ ref('stg_calendar__sessions') }} as s
        on q.available_date = s.session_date
),
-- Latest version of every quarter known at each event.
known as (
    select
        e.security_id, e.metric, e.event_date,
        q.period_start, q.period_end, q.value, q.available_date
    from events as e
    inner join quarters as q
        on e.security_id = q.security_id
        and e.metric = q.metric
        and q.available_ts < e.cutoff_ts
    qualify row_number() over (
        partition by e.security_id, e.metric, e.event_date, q.period_end
        order by q.available_ts desc, q.accession_number desc
    ) = 1
),
last_four as (
    select *
    from known
    qualify row_number() over (
        partition by security_id, metric, event_date order by period_end desc
    ) <= 4
),
-- Lag after the filter, so the earliest of the four has no predecessor.
chained as (
    select
        *,
        period_start = lag(period_end) over (
            partition by security_id, metric, event_date order by period_end
        ) + 1 as follows_previous
    from last_four
)
select
    security_id,
    metric || '_ttm' as metric,
    event_date,
    max(period_end) as period_end,
    case
        -- The earliest's follows_previous is null; the other three must be true.
        when count(*) = 4 and count(*) filter (where follows_previous) = 3 then sum(value)
    end as value,
    max(available_date) as source_available_date
from chained
group by security_id, metric, event_date
