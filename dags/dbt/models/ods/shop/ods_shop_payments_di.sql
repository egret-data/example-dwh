{#
  Daily increment of shop.payments for the Vietnam business day dt (spec D12).
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

{% set tz = source_timezone('shop', 'payments') %}

select
    cast(payment_id as varchar)       as payment_id,
    cast(order_id as bigint)          as order_id,
    cast(customer_id as bigint)       as customer_id,
    cast(shop_id as bigint)           as shop_id,
    cast(amount as decimal(18, 2))    as amount,
    cast(method as varchar)           as method,
    {{ source_ts('paid_at', tz) }}    as paid_at,
    {{ source_ts('updated_at', tz) }} as updated_at,
    date '{{ get_dt() }}'             as dt
from {{ source('shop', 'payments') }}
where {{ in_business_day('updated_at', tz) }}
