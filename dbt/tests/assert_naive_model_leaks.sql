-- Test the test: the same check must find leakage in the deliberately leaky
-- model. If it finds none, assert_no_lookahead passing proves nothing.
select count(*) as leaking_rows
from ({{ lookahead_rows(ref('fct_features_daily_naive')) }})
having count(*) = 0
