{#
  Accumulating snapshot of the order lifecycle (process order_lifecycle): one row per order, merged on order_id
  and partitioned by the order's event day. Hand-written because the scaffold refuses accumulating processes.
  Reads DWD only (STD-01-05). A run for dt D touches the orders placed on D and the orders paid on D, and writes
  each order's full current state; an order paid on a later day updates its existing row in its original partition.
#}
{{
  config(
    incremental_strategy='merge',
    unique_key='order_id',
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

with touched as (
    select order_id
    from {{ ref('dwd_trade_order_di') }}
    where dt = date '{{ get_dt() }}'
    union distinct
    select order_id
    from {{ ref('dwd_trade_payment_di') }}
    where dt = date '{{ get_dt() }}'
),

orders as (
    select
        order_id,
        order_date_key,
        customer_key,
        shop_key,
        order_amt,
        created_at,
        dt
    from {{ ref('dwd_trade_order_di') }}
    where order_id in (select order_id from touched)
),

payments as (
    select
        order_id,
        min(paid_at)                         as paid_at,
        cast(sum(pay_amt) as decimal(18, 2)) as pay_amt
    from {{ ref('dwd_trade_payment_di') }}
    -- All payments, not only up to dt: the row holds the order's current state. A payment whose order is not
    -- in the order DWD yet is picked up when the order day is re-run (STD-05-08 late rows).
    where order_id in (select order_id from touched)
    group by order_id
)

select
    o.order_id,
    o.order_date_key,
    case
        when p.paid_at is null then '-2'
        else {{ dbt_utils.generate_surrogate_key(
            ["cast(p.paid_at at time zone 'Asia/Ho_Chi_Minh' as date)"]
        ) }}
    end                   as pay_date_key,
    o.customer_key,
    o.shop_key,
    o.order_amt,
    p.pay_amt,
    o.created_at,
    p.paid_at,
    p.paid_at is not null as is_paid,
    o.dt
from orders as o
left join payments as p
    on o.order_id = p.order_id
