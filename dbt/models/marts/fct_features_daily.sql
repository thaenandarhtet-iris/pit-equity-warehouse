-- Point-in-time features: one row per (trade_date, security_id) in the
-- universe. Each metric is the latest snapshot event on or before trade_date
-- (ASOF LEFT JOIN), so every value was available before that session opened,
-- and <metric>_source_available_date records when it became available.
with events as (
    select security_id, metric, event_date, period_end, value, available_date as source_available_date
    from {{ ref('int_fundamentals__snapshot_events') }}
    union all
    select security_id, metric, event_date, period_end, value, source_available_date
    from {{ ref('int_fundamentals__ttm_events') }}
),
{{ daily_features() }}
