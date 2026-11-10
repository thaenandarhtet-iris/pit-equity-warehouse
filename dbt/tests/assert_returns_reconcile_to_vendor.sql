-- Each day's return from raw fields must match the day-over-day ratio of
-- Tiingo's back-adjusted close within 1e-4. Compared daily, not compounded,
-- so vendor rounding can't add up and a failure names the day. Failing rows
-- are stored (store_failures) so the README can count and list them.
{{ config(store_failures=true) }}

select
    security_id,
    price_symbol,
    trade_date,
    daily_return,
    vendor_return,
    daily_return - vendor_return as difference
from {{ ref('fct_prices_daily') }}
where abs(daily_return - vendor_return) > 1e-4
