-- Each security's rows must tile its history: every row starts where the
-- previous one ended, intervals are non-empty, and only the last is open.
with ordered as (
    select
        security_id,
        valid_from,
        valid_to,
        lag(valid_to) over w as prev_valid_to,
        lead(valid_from) over w as next_valid_from
    from {{ ref('dim_security') }}
    window w as (partition by security_id order by valid_from)
)
select *
from ordered
where valid_to <= valid_from
    or (prev_valid_to is not null and prev_valid_to != valid_from)
    or (valid_to is null and next_valid_from is not null)
    or (valid_to is not null and next_valid_from is null)
