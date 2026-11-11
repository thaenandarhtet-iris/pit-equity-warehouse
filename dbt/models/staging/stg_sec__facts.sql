select
    cik,
    taxonomy,
    tag,
    unit,
    val as value,
    period_start,
    period_end,
    -- fy/fp describe the filing that reported the fact, not the fact's period:
    -- a 2018 10-K repeats 2017 numbers with fy = 2018.
    fy as filing_fiscal_year,
    fp as filing_fiscal_period,
    form,
    filed as filed_date,
    accn as accession_number,
    frame
from {{ source('sec', 'sec_facts') }}
