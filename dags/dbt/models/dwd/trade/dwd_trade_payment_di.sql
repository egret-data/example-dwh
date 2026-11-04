{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

-- Process payment. Grain: One row per payment, on the Asia/Ho_Chi_Minh day it was captured.
-- Durable keys: hash of the dimension's natural key (a role hashes its own column, e.g. ship_date;
-- a single date role is derived from the event column).
-- Event fact (STD-05-08): dt is the Vietnam day of paid_at. A run reads every ODS partition from dt on
-- and keeps the earliest version of each grain key: the state at the end of the event day.
with versions as (
    select
        payment_id,
        order_id,
        amount,
        method,
        paid_at,
        customer_id,
        shop_id,
        dt,
        row_number() over (partition by payment_id order by dt) as version_rank
    from {{ ref('ods_shop_payments_di') }}
    where
        dt >= date '{{ get_dt() }}'
        and {{ in_business_day_tz('paid_at') }}
)

select
    payment_id,
    order_id,
    case
        when paid_at is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(
            ["cast(paid_at at time zone 'Asia/Ho_Chi_Minh' as date)"]
        ) }}
    end                   as pay_date_key,
    case
        when customer_id is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(['customer_id']) }}
    end                   as customer_key,
    case
        when shop_id is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(['shop_id']) }}
    end                   as shop_key,
    amount                as pay_amt,
    method,
    paid_at,
    date '{{ get_dt() }}' as dt
from versions
where version_rank = 1
