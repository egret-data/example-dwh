{{
  config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='id',
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

select cast(id as bigint) as id, cast(v as varchar) as v, dt
from (
{% if var('batch') | int == 1 %}
    values (1, 'a', date '2026-11-01'), (2, 'b', date '2026-11-01')
{% else %}
    values (2, 'b2', date '2026-11-02'), (3, 'c', date '2026-11-02')
{% endif %}
) as t (id, v, dt)
