select trade_date, security_id, count(*) as n
from {{ ref('fct_features_daily') }}
group by all
having count(*) > 1
