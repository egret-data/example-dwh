{{ config(materialized='table') }}

-- One current row per natural key (spec D11); the durable key is a hash of the natural key.
-- A df upstream: its latest partition is the current state.
-- The unknown ('-1') and not applicable ('-2') members have a null natural key and text labels (STD-04-06).
with current_members as (
    select
        {{ dbt_utils.generate_surrogate_key(['customer_id']) }} as customer_key,
        customer_id,
        customer_name,
        city,
        updated_at
    from {{ ref('ods_shop_customers_df') }}
    where dt = (select max(dt) from {{ ref('ods_shop_customers_df') }})
),

special_members as (
    select
        '-1'                                as customer_key,
        cast(null as bigint)                as customer_id,
        'Unknown'                           as customer_name,
        'Unknown'                           as city,
        timestamp '1900-01-01 00:00:00 UTC' as updated_at
    union all
    select
        '-2'                                as customer_key,
        cast(null as bigint)                as customer_id,
        'Not applicable'                    as customer_name,
        'Not applicable'                    as city,
        timestamp '1900-01-01 00:00:00 UTC' as updated_at
)

select
    customer_key,
    customer_id,
    customer_name,
    city,
    updated_at
from current_members
union all
select
    customer_key,
    customer_id,
    customer_name,
    city,
    updated_at
from special_members
