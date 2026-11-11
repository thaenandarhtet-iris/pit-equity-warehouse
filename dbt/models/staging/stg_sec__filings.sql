select
    cik,
    accession_number,
    form,
    filing_date,
    report_date,
    -- EDGAR's trailing Z is real UTC (checked against index pages; see
    -- docs/decisions.md), so the timestamp is stored as naive UTC.
    cast(replace(replace(acceptance_datetime, 'T', ' '), 'Z', '') as timestamp) as accepted_at_utc
from {{ source('sec', 'sec_filings') }}
