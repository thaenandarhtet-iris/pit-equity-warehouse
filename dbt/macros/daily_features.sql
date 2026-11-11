{# Shared tail of fct_features_daily and fct_features_daily_naive. Expects a
   CTE named `events` (security_id, metric, event_date, period_end, value,
   source_available_date) and continues the WITH clause from there: ASOF join
   the universe grid onto it, pivot to one column per metric, add the ratios.
   The two models differ only in how `events` is built. #}
{% macro daily_features() %}
{%- set metrics = feature_metrics() %}
grid as (
    select u.trade_date, u.security_id, m.metric
    from {{ ref('fct_universe_daily') }} as u
    cross join (
        select unnest([{% for m in metrics %}'{{ m }}'{{ "," if not loop.last }}{% endfor %}]) as metric
    ) as m
),
pit as (
    select g.trade_date, g.security_id, g.metric, e.value, e.source_available_date
    from grid as g
    asof left join events as e
        on g.security_id = e.security_id
        and g.metric = e.metric
        and g.trade_date >= e.event_date
),
wide as (
    select
        trade_date,
        security_id,
        {%- for m in metrics %}
        max(value) filter (where metric = '{{ m }}') as {{ m }},
        max(source_available_date) filter (where metric = '{{ m }}') as {{ m }}_source_available_date
        {{- "," if not loop.last }}
        {%- endfor %}
    from pit
    group by trade_date, security_id
)
select
    w.*,
    p.close,
    p.close * w.shares_outstanding as market_cap,
    case when w.net_income_ttm > 0 then p.close * w.shares_outstanding / w.net_income_ttm end as pe_ttm,
    case when w.stockholders_equity > 0 then p.close * w.shares_outstanding / w.stockholders_equity end as pb,
    w.total_liabilities / nullif(w.stockholders_equity, 0) as debt_to_equity
from wide as w
left join {{ ref('fct_prices_daily') }} as p
    on w.security_id = p.security_id
    and w.trade_date = p.trade_date
{% endmacro %}
