-- Raw, unadjusted prices. adj_close is kept only to reconcile our own returns
-- against; it is back-adjusted with future splits, so features must not use it.
select
    ticker as price_symbol,
    trade_date,
    open,
    high,
    low,
    close,
    volume,
    div_cash,
    split_factor,
    adj_close as vendor_adj_close
from {{ source('tiingo', 'prices_daily') }}
