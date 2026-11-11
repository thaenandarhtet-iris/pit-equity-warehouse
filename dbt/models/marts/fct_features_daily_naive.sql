-- DELIBERATELY LEAKY. Exists only to be compared with fct_features_daily and
-- to prove assert_no_lookahead can fail. Never use it for research.
--
-- This is the common shortcut: key each value on its fiscal period_end (as if
-- it were known the day the quarter closed) and always use the latest version
-- (restated values leak back to the original date). It leaks twice: the
-- filing lag, and restatements.
with latest as (
    select security_id, metric, period_start, period_end, value, available_date
    from {{ ref('int_fundamentals__versions') }}
    qualify row_number() over (
        partition by security_id, metric, period_end order by available_ts desc, accession_number desc
    ) = 1
),
flows as (
    select
        *,
        coalesce(period_start = lag(period_end) over (partition by security_id, metric order by period_end) + 1, false)
            as follows_previous
    from latest
    where metric in ('revenue', 'net_income')
),
-- Same four-consecutive-quarters rule as the PIT model; only the leak differs.
ttm as (
    select
        security_id,
        metric || '_ttm' as metric,
        period_end,
        case
            when count(*) over w = 4
                and count(*) filter (where follows_previous) over w3 = 3
                then sum(value) over w
        end as value,
        max(available_date) over w as source_available_date
    from flows
    window
        w as (partition by security_id, metric order by period_end rows between 3 preceding and current row),
        w3 as (partition by security_id, metric order by period_end rows between 2 preceding and current row)
),
events as (
    select security_id, metric, period_end as event_date, period_end, value, available_date as source_available_date
    from latest
    union all
    select security_id, metric, period_end as event_date, period_end, value, source_available_date
    from ttm
),
{{ daily_features() }}
