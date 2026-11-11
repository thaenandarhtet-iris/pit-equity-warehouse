select
    cik,
    name as company_name,
    tickers as current_tickers,
    fiscal_year_end,
    sic_description
from {{ source('sec', 'sec_companies') }}
