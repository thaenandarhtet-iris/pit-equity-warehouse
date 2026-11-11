select
    -- The security's own key: its latest SEC CIK, or a negative ID for a
    -- security that never filed with the SEC.
    cast(security_id as bigint) as security_id,
    ticker,
    cast(start_date as date) as start_date,
    -- Null while the ticker is still in the index.
    cast(end_date as date) as end_date,
    resolution as cik_resolution
from {{ source('universe', 'universe_membership') }}
