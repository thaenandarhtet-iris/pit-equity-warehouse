-- Each day's return from raw fields must match the day-over-day ratio of
-- Tiingo's back-adjusted close within 1e-4. Compared daily, not compounded,
-- so vendor rounding can't add up and a failure names the day. Failing rows
-- are stored (store_failures) so the README can count and list them.
-- Days reviewed and traced to a vendor-side error are listed, with the
-- evidence, in the reconciliation_exceptions seed; any other mismatch fails.
{{ config(store_failures=true) }}

select
    p.security_id,
    p.price_symbol,
    p.trade_date,
    p.daily_return,
    p.vendor_return,
    p.daily_return - p.vendor_return as difference
from {{ ref('fct_prices_daily') }} as p
left join {{ ref('reconciliation_exceptions') }} as e
    on p.security_id = e.security_id and p.trade_date = e.trade_date
where abs(p.daily_return - p.vendor_return) > 1e-4
    and e.security_id is null
