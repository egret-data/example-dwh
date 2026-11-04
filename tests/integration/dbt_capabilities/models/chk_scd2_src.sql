{{ config(materialized='table') }}

select cast(id as bigint) as id, cast(v as varchar) as v
from (
{% if var('batch') | int == 1 %}
    values (1, 'a'), (2, 'b')
{% else %}
    values (1, 'a2'), (2, 'b')
{% endif %}
) as t (id, v)
