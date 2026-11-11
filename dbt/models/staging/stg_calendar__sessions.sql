select
    cast(session_date as date) as session_date,
    cast(market_open_utc as timestamp) as market_open_utc,
    cast(market_close_utc as timestamp) as market_close_utc
from {{ ref('trading_calendar') }}
