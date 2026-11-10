-- A derived Q4 subtracts the 9-month value from the annual one, so it cannot be
-- known before the 10-K that reports the annual value was accepted.
select q.*
from {{ ref('int_facts__discrete_quarters') }} as q
inner join {{ ref('int_filings__availability') }} as f
    on q.cik = f.cik
    and q.accession_number = f.accession_number
where q.derived_from = 'fiscal_year'
    and q.available_ts < f.available_ts
