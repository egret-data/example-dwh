{{
  config(
    incremental_strategy='delete+insert',
    unique_key=['dt'],
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set dt = get_dt() %}

select
    cast(customer_id as bigint)      as customer_id,
    cast(customer_name as varchar)   as customer_name,
    cast(city as varchar)            as city,
    cast(created_at as timestamp(6)) as created_at,
    cast(updated_at as timestamp(6)) as updated_at,
    date '{{ dt }}'                  as dt
from {{ source('shop', 'customers') }}
