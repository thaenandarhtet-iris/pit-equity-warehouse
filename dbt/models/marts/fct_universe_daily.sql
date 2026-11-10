-- One row per (session, security) for every security in the index that day,
-- including names that later left or were delisted. This grid, not the list
-- of companies that exist today, is what makes the sample survivorship-free.
select
    c.session_date as trade_date,
    d.security_id,
    d.tickers
from {{ ref('stg_calendar__sessions') }} as c
inner join {{ ref('dim_security') }} as d
    on d.is_member
    and c.session_date >= d.valid_from
    and (d.valid_to is null or c.session_date < d.valid_to)
where c.session_date between date '{{ var("universe_start") }}' and date '{{ var("universe_end") }}'
