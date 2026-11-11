-- Naive vs point-in-time, per metric (SPEC section 9, leakage). A naive row is
-- leaky when its value differs from the PIT value or its source was not yet
-- available on the trade date. Look-ahead days count how far in the future
-- the naive source was.
{%- set metrics = feature_metrics() %}
with paired as (
    {%- for m in metrics %}
    select
        '{{ m }}' as metric,
        n.{{ m }} as naive_value,
        p.{{ m }} as pit_value,
        n.{{ m }}_source_available_date - n.trade_date as naive_lead_days
    from {{ ref('fct_features_daily_naive') }} as n
    inner join {{ ref('fct_features_daily') }} as p
        using (trade_date, security_id)
    {{ "union all" if not loop.last }}
    {%- endfor %}
),
compared as (
    select
        metric,
        count(*) filter (where naive_value is not null) as naive_rows,
        count(*) filter (
            where naive_value is not null
                and (naive_value is distinct from pit_value or naive_lead_days > 0)
        ) as leaky_rows,
        count(*) filter (where naive_value is not null and naive_lead_days > 0) as lookahead_rows,
        median(naive_lead_days) filter (where naive_value is not null and naive_lead_days > 0)
            as median_lookahead_days,
        quantile_cont(naive_lead_days, 0.9) filter (where naive_value is not null and naive_lead_days > 0)
            as p90_lookahead_days
    from paired
    group by metric
),
versions as (
    select
        metric,
        count(*) filter (where is_restatement) as restated_versions,
        count(*) filter (where is_derived) as derived_quarter_versions
    from {{ ref('int_fundamentals__versions') }}
    group by metric
)
select
    c.metric,
    c.naive_rows,
    c.leaky_rows,
    round(100.0 * c.leaky_rows / nullif(c.naive_rows, 0), 2) as pct_leaky,
    c.lookahead_rows,
    c.median_lookahead_days,
    c.p90_lookahead_days,
    v.restated_versions,
    v.derived_quarter_versions
from compared as c
-- A TTM metric's restatements and derived quarters are its quarterly metric's.
left join versions as v
    on replace(c.metric, '_ttm', '') = v.metric
order by c.metric
