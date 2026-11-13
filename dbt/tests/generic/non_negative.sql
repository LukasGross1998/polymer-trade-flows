{#- Fails for every row where the column is negative (nulls pass). -#}
{% test non_negative(model, column_name) %}
select *
from {{ model }}
where {{ column_name }} < 0
{% endtest %}
