-- A security's filings come from each of its filers in turn: [valid_from,
-- valid_to) on acceptance date, null meaning open. A reorganized company
-- (Exxon Mobil Corp, then ExxonMobil Holdings) has one row per filer.
select
    cast(security_id as bigint) as security_id,
    cast(cik as bigint) as cik,
    cast(valid_from as date) as valid_from,
    cast(valid_to as date) as valid_to
from {{ source('universe', 'universe_filers') }}
