{#
  Daily full copy of shop.shops into the Vietnam business day dt (spec D12).
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

{% set tz = source_timezone('shop', 'shops') %}

select
    cast(shop_id as bigint)           as shop_id,
    cast(shop_name as varchar)        as shop_name,
    cast(city as varchar)             as city,
    {{ source_ts('created_at', tz) }} as created_at,
    {{ source_ts('updated_at', tz) }} as updated_at,
    date '{{ get_dt() }}'             as dt
from {{ source('shop', 'shops') }}
