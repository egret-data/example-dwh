{{
  config(
    incremental_strategy='delete+insert',
    unique_key=['dt'],
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set dt = get_dt() %}

select
    cast(order_id as bigint)            as order_id,
    cast(customer_id as bigint)         as customer_id,
    cast(order_status as varchar)       as order_status,
    cast(total_amount as decimal(18, 2)) as total_amount,
    cast(created_at as timestamp(6))    as created_at,
    cast(updated_at as timestamp(6))    as updated_at,
    date '{{ dt }}'                     as dt
from {{ source('shop', 'orders') }}
where updated_at >= timestamp '{{ dt }} 00:00:00'
  and updated_at < timestamp '{{ dt }} 00:00:00' + interval '1' day
