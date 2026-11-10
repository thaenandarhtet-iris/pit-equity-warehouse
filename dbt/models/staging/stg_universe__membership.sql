select
    cast(cik as bigint) as cik,
    ticker,
    cast(start_date as date) as start_date,
    -- Null while the ticker is still in the index.
    cast(end_date as date) as end_date,
    resolution as cik_resolution
from {{ source('universe', 'universe_membership') }}
