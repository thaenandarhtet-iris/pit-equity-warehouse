-- Quarter-length versions of flow metrics. 10-Qs often report year-to-date
-- values and there is no Q4 10-Q, so missing quarters are derived by
-- subtraction (Q2 = 6M - Q1, Q3 = 9M - 6M, Q4 = FY - 9M).
--
-- A derived version uses the earlier cumulative value as it was known when the
-- later filing was accepted, and is available only once both inputs are: a
-- derived Q4 can never be known before its 10-K.
with flows as (
    select
        security_id, metric, duration_class, value, period_start, period_end,
        accession_number, available_ts, available_date
    from {{ ref('int_facts__mapped') }}
    where duration_class != 'instant'
),

direct as (
    select
        security_id, metric, period_start, period_end, value, accession_number,
        available_ts, available_date,
        false as is_derived,
        cast(null as varchar) as derived_from
    from flows
    where duration_class = 'quarter'
),

-- EPS is not additive across quarters (share counts change), so it is never derived.
cumulative as (
    select
        *,
        case duration_class
            when 'ytd_6m' then 'quarter'
            when 'ytd_9m' then 'ytd_6m'
            when 'fiscal_year' then 'ytd_9m'
        end as prior_class
    from flows
    where duration_class in ('ytd_6m', 'ytd_9m', 'fiscal_year')
        and metric in ('revenue', 'net_income')
),

prior_periods as (
    select distinct security_id, metric, duration_class, period_start, period_end
    from flows
),

with_prior_period as (
    select c.*, max(p.period_end) as prior_end
    from cumulative as c
    inner join prior_periods as p
        on c.security_id = p.security_id
        and c.metric = p.metric
        and c.period_start = p.period_start
        and c.prior_class = p.duration_class
        and p.period_end < c.period_end
    group by all
),

-- Latest version of the earlier cumulative period accepted no later than this one.
known_prior as (
    select
        w.*,
        f.value as prior_value,
        f.available_ts as prior_ts,
        f.available_date as prior_date
    from with_prior_period as w
    asof left join flows as f
        on w.security_id = f.security_id
        and w.metric = f.metric
        and w.period_start = f.period_start
        and w.prior_end = f.period_end
        and w.available_ts >= f.available_ts
),

-- If the earlier period was only ever reported after this filing, its first
-- version is used and the derived value waits for it.
first_version as (
    select
        security_id, metric, period_start, period_end,
        arg_min(value, available_ts) as value,
        min(available_ts) as available_ts,
        min(available_date) as available_date
    from flows
    group by all
),

derived as (
    select
        k.security_id,
        k.metric,
        k.prior_end + 1 as period_start,
        k.period_end,
        k.value - coalesce(k.prior_value, v.value) as value,
        k.accession_number,
        greatest(k.available_ts, coalesce(k.prior_ts, v.available_ts)) as available_ts,
        greatest(k.available_date, coalesce(k.prior_date, v.available_date)) as available_date,
        true as is_derived,
        k.duration_class as derived_from
    from known_prior as k
    left join first_version as v
        on k.security_id = v.security_id
        and k.metric = v.metric
        and k.period_start = v.period_start
        and k.prior_end = v.period_end
)

select * from direct
union all
-- A directly reported quarter wins over a derived one known no earlier.
select d.*
from derived as d
where not exists (
    select 1
    from direct as q
    where q.security_id = d.security_id
        and q.metric = d.metric
        and q.period_end = d.period_end
        and q.available_ts <= d.available_ts
)
