-- One row per (security, metric, period, filing). The best tag is picked within
-- each filing, not across filings: filers re-tag old periods in later
-- comparatives, and choosing across filings would discard the original version.
-- A period is its end date and duration class: a filing can tag the same
-- quarter in a second context with a shifted start (J.B. Hunt's Q2 2013, 87
-- days, rounded), and the full span is the period as reported.
with facts as (
    select
        a.security_id,
        m.metric,
        f.tag,
        m.priority,
        m.period_type,
        f.unit,
        f.value,
        f.period_start,
        f.period_end,
        f.accession_number,
        f.form,
        a.available_ts,
        a.available_date,
        f.period_end - f.period_start as duration_days
    from {{ ref('stg_sec__facts') }} as f
    inner join {{ ref('concept_map') }} as m
        on f.taxonomy = m.taxonomy
        and f.tag = m.tag
        and f.unit = m.unit
    inner join {{ ref('int_filings__availability') }} as a
        on f.cik = a.cik
        and f.accession_number = a.accession_number
),

classified as (
    select
        *,
        case
            when period_type = 'instant' then 'instant'
            when duration_days between 80 and 100 then 'quarter'
            when duration_days between 170 and 190 then 'ytd_6m'
            when duration_days between 260 and 280 then 'ytd_9m'
            when duration_days between 350 and 380 then 'fiscal_year'
        end as duration_class
    from facts
    -- An instant tag reported with a start date (or the reverse) is mis-tagged.
    where (period_type = 'instant') = (period_start is null)
)

select * exclude (rn)
from (
    select
        *,
        row_number() over (
            partition by security_id, metric, duration_class, period_end, accession_number
            order by priority, duration_days desc, tag
        ) as rn
    from classified
    where duration_class is not null
)
where rn = 1
