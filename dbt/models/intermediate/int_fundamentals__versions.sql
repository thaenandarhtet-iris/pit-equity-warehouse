-- Every version of every (company, metric, period), each with its own
-- availability. Nothing is collapsed to "latest value wins" here; the
-- point-in-time choice happens in int_fundamentals__snapshot_events.
with flows as (
    select
        security_id, metric, period_start, period_end, value, accession_number,
        available_ts, available_date, is_derived, derived_from
    from {{ ref('int_facts__discrete_quarters') }}
),

instants as (
    select
        security_id, metric, period_start, period_end, value, accession_number,
        available_ts, available_date,
        false as is_derived,
        cast(null as varchar) as derived_from
    from {{ ref('int_facts__mapped') }}
    where duration_class = 'instant'
),

versions as (
    select * from flows
    union all
    select * from instants
)

select
    *,
    row_number() over w as version_number,
    -- Relative tolerance 1e-6 so rounding noise is not counted as a restatement.
    abs(value - first_value(value) over w)
        > 1e-6 * abs(first_value(value) over w)
        as is_restatement
from versions
window w as (
    partition by security_id, metric, period_end
    order by available_ts, accession_number
    rows between unbounded preceding and current row
)
