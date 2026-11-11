-- The headline test: no feature value may come from a source that became
-- available after the trade date. assert_naive_model_leaks proves this query
-- does catch leakage when it exists.
{{ lookahead_rows(ref('fct_features_daily')) }}
