{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}
-- depends_on: {{ ref('dim_pub_customer') }}

-- One statistical period per table (nd); metric columns follow warehouse/metrics.yml.
select
    customer_key,
    sum(order_amt) as order_amt_sum_30d,
    date '{{ get_dt() }}' as dt
from {{ ref('dwd_trade_order_di') }}
where
    dt > date '{{ get_dt() }}' - interval '30' day
    and dt <= date '{{ get_dt() }}'
group by customer_key
