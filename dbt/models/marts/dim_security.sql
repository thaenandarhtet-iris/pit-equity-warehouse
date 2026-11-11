-- SCD2 on the security: a new row whenever the set of index tickers changes, including
-- joining or leaving the index. Intervals are [valid_from, valid_to); a null
-- valid_to is open. tickers lists every share class in the index at once
-- (GOOG,GOOGL). Rows outside the index have null tickers: tickers are only
-- tracked while a member.
with membership as (
    select security_id, ticker, start_date, end_date
    from {{ ref('stg_universe__membership') }}
),
bounds as (
    select security_id, start_date as bound from membership
    union
    select security_id, end_date from membership where end_date is not null
),
segments as (
    select security_id, bound as valid_from, lead(bound) over (partition by security_id order by bound) as valid_to
    from bounds
),
members as (
    select
        s.security_id,
        s.valid_from,
        s.valid_to,
        string_agg(m.ticker, ',' order by m.ticker) as tickers
    from segments as s
    left join membership as m
        on s.security_id = m.security_id
        and m.start_date <= s.valid_from
        and (m.end_date is null or m.end_date > s.valid_from)
    group by all
)
select
    m.security_id,
    m.valid_from,
    m.valid_to,
    m.tickers,
    m.tickers is not null as is_member,
    m.valid_to is null as is_current,
    s.security_name,
    s.price_symbol,
    s.is_departed
from members as m
inner join {{ ref('stg_universe__securities') }} as s
    on m.security_id = s.security_id
