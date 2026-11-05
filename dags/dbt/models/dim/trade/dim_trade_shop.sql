{{ config(materialized='table') }}

-- One current row per natural key (spec D11); the durable key is a hash of the natural key.
-- A df upstream: its latest partition is the current state.
-- The unknown ('-1') and not applicable ('-2') members have a null natural key and text labels (STD-04-06).
with current_members as (
    select
        {{ dbt_utils.generate_surrogate_key(['shop_id']) }} as shop_key,
        shop_id,
        shop_name,
        city
    from {{ ref('ods_shop_shops_df') }}
    where dt = (select max(dt) from {{ ref('ods_shop_shops_df') }})
),

special_members as (
    select
        '-1'                 as shop_key,
        cast(null as bigint) as shop_id,
        'Unknown'            as shop_name,
        'Unknown'            as city
    union all
    select
        '-2'                 as shop_key,
        cast(null as bigint) as shop_id,
        'Not applicable'     as shop_name,
        'Not applicable'     as city
)

select
    shop_key,
    shop_id,
    shop_name,
    city
from current_members
union all
select
    shop_key,
    shop_id,
    shop_name,
    city
from special_members
