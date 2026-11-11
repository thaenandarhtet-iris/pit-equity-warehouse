-- A filing is usable from the first session whose open is strictly after its
-- acceptance: accepted 16:05 ET Tuesday -> Wednesday; 08:00 ET Wednesday ->
-- Wednesday; Friday after the close or before a holiday -> next session.
-- A filing accepted before the calendar starts gets the first session.
--
-- Each filing is assigned to the security its filer reported for on the
-- acceptance date. A predecessor that keeps filing as a subsidiary after a
-- reorganization (Xerox Corp after 2019-07-31) no longer counts.
select
    r.security_id,
    f.cik,
    f.accession_number,
    f.form,
    f.accepted_at_utc as available_ts,
    s.session_date as available_date
from {{ ref('stg_sec__filings') }} as f
inner join {{ ref('stg_universe__filers') }} as r
    on f.cik = r.cik
    and (r.valid_from is null or cast(f.accepted_at_utc as date) >= r.valid_from)
    and (r.valid_to is null or cast(f.accepted_at_utc as date) < r.valid_to)
asof left join {{ ref('stg_calendar__sessions') }} as s
    on f.accepted_at_utc < s.market_open_utc
