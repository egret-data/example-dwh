{#
  Daily full copy of shop.customers into the Vietnam business day dt (spec D12).
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

{% set tz = source_timezone('shop', 'customers') %}

select
    cast(customer_id as bigint)       as customer_id,
    cast(customer_name as varchar)    as customer_name,
    cast(city as varchar)             as city,
    {{ source_ts('created_at', tz) }} as created_at,
    {{ source_ts('updated_at', tz) }} as updated_at,
    date '{{ get_dt() }}'             as dt
from {{ source('shop', 'customers') }}
