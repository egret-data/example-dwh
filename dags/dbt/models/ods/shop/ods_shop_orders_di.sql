{#
  Daily increment of shop.orders for the Vietnam business day dt (spec D12).
  Replace the dt partition: delete it first, then append the batch. Unlike delete+insert keyed
  on dt, this also clears the partition when the re-run batch is empty.
#}
{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set tz = source_timezone('shop', 'orders') %}

select
    cast(order_id as bigint)             as order_id,
    cast(customer_id as bigint)          as customer_id,
    cast(shop_id as bigint)              as shop_id,
    cast(channel as varchar)             as channel,
    cast(order_status as varchar)        as order_status,
    cast(total_amount as decimal(18, 2)) as total_amount,
    {{ source_ts('created_at', tz) }}    as created_at,
    {{ source_ts('updated_at', tz) }}    as updated_at,
    date '{{ get_dt() }}'                as dt
from {{ source('shop', 'orders') }}
where {{ in_business_day('updated_at', tz) }}
