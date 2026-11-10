-- A filing is usable from the first session whose open is strictly after its
-- acceptance: accepted 16:05 ET Tuesday -> Wednesday; 08:00 ET Wednesday ->
-- Wednesday; Friday after the close or before a holiday -> next session.
-- A filing accepted before the calendar starts gets the first session.
select
    f.cik,
    f.accession_number,
    f.form,
    f.accepted_at_utc as available_ts,
    s.session_date as available_date
from {{ ref('stg_sec__filings') }} as f
asof left join {{ ref('stg_calendar__sessions') }} as s
    on f.accepted_at_utc < s.market_open_utc
