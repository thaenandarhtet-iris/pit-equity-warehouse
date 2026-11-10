select
    cast(cik as bigint) as cik,
    name as security_name,
    is_departed,
    -- Null when Tiingo serves no history covering the membership window.
    price_symbol
from {{ source('universe', 'universe_securities') }}
