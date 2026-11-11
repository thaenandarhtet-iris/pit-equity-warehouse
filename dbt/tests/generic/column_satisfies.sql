{% test column_satisfies(model, column_name, condition) %}
-- Fails on rows where the column is non-null and the condition is false,
-- e.g. condition "> 0".
select *
from {{ model }}
where {{ column_name }} is not null
  and not ({{ column_name }} {{ condition }})
{% endtest %}
