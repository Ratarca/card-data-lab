{% test dbt_utils_accepts_range(model, column_name, min, max) %}
select *
from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ min }} or {{ column_name }} > {{ max }})
{% endtest %}
