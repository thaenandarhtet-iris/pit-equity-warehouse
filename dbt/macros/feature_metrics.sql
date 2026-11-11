{# Metrics carried into the daily feature marts, each with its own
   <metric>_source_available_date column. One list so the PIT model, the naive
   model and assert_no_lookahead can't drift apart. #}
{% macro feature_metrics() %}
    {{ return([
        'eps_diluted', 'total_assets', 'total_liabilities', 'stockholders_equity',
        'shares_outstanding', 'revenue_ttm', 'net_income_ttm'
    ]) }}
{% endmacro %}
