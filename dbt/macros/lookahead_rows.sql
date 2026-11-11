{# Rows of a daily feature model where any metric's source became available
   after the trade date. #}
{% macro lookahead_rows(model) %}
select *
from {{ model }}
where {% for m in feature_metrics() -%}
    {{ m }}_source_available_date > trade_date
    {%- if not loop.last %} or {% endif %}
{% endfor %}
{% endmacro %}
