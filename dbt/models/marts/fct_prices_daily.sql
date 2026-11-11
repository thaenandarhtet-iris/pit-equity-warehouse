-- Raw close plus a daily total return built only from that day's raw fields
-- and the previous session's close, so history never changes after a later
-- split. Tiingo quotes div_cash per share as of the day, after any split that
-- day, hence (close + div) * split. vendor_return (from the back-adjusted
-- adj_close) is kept only for the reconciliation test.
with prices as (
    select
        s.security_id,
        p.price_symbol,
        p.trade_date,
        p.close,
        p.div_cash,
        p.split_factor,
        p.vendor_adj_close,
        lag(p.close) over w as prev_close,
        lag(p.vendor_adj_close) over w as prev_vendor_adj_close
    from {{ ref('stg_prices__daily') }} as p
    inner join {{ ref('stg_universe__securities') }} as s
        on p.price_symbol = s.price_symbol
    -- Per security, not per symbol: two securities can share one series (old
    -- DuPont and DuPont de Nemours both use DD).
    window w as (partition by s.security_id order by p.trade_date)
)
select
    security_id,
    price_symbol,
    trade_date,
    close,
    div_cash,
    split_factor,
    (close + div_cash) * split_factor / prev_close - 1 as daily_return,
    vendor_adj_close / prev_vendor_adj_close - 1 as vendor_return
from prices
