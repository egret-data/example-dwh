{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}
-- depends_on: {{ ref('dim_pub_customer') }}
-- depends_on: {{ ref('dim_pub_date') }}
-- depends_on: {{ ref('dim_trade_shop') }}

-- Process order. Grain: One row per order, on the Asia/Ho_Chi_Minh day it was placed.
-- Durable keys: hash of the dimension's natural key (a role hashes its own column, e.g. ship_date;
-- a single date role is derived from the event column).
-- Event fact (STD-05-08): dt is the Vietnam day of created_at. A run reads every ODS partition from dt on
-- and keeps the earliest version of each grain key: the state at the end of the event day.
with versions as (
    select
        order_id,
        channel,
        order_status,
        total_amount,
        created_at,
        customer_id,
        shop_id,
        dt,
        row_number() over (partition by order_id order by dt) as version_rank
    from {{ ref('ods_shop_orders_di') }}
    where
        dt >= date '{{ get_dt() }}'
        and {{ in_business_day_tz('created_at') }}
),

-- Point-in-time city (STD-05-05): each key's earliest version is valid since 1900, so an order placed
-- before the first snapshot takes the first known version.
history as (
    select
        customer_key,
        city,
        case
            when valid_from = min(valid_from) over (partition by customer_key)
                then timestamp '1900-01-01 00:00:00 UTC'
            else valid_from
        end as valid_from,
        valid_to
    from {{ ref('dim_pub_customer_hist') }}
)

select
    o.order_id,
    case
        when o.created_at is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(
            ["cast(o.created_at at time zone 'Asia/Ho_Chi_Minh' as date)"]
        ) }}
    end                         as order_date_key,
    case
        when o.customer_id is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(['o.customer_id']) }}
    end                         as customer_key,
    case
        when o.shop_id is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(['o.shop_id']) }}
    end                         as shop_key,
    o.channel,
    o.order_status,
    o.total_amount              as order_amt,
    coalesce(h.city, 'Unknown') as customer_city,
    o.created_at,
    date '{{ get_dt() }}'       as dt
from versions as o
left join history as h
    on
        h.customer_key = {{ dbt_utils.generate_surrogate_key(['o.customer_id']) }}
        and o.created_at >= h.valid_from
        and (o.created_at < h.valid_to or h.valid_to is null)
where o.version_rank = 1
