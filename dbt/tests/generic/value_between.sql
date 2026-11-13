{#- Fails for every row where the column lies outside [min_value, max_value] (nulls pass). -#}
{% test value_between(model, column_name, min_value, max_value) %}
select *
from {{ model }}
where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}
