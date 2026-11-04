{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}
-- depends_on: {{ ref('dim_pub_customer') }}

-- One statistical period per table (1d); metric columns follow warehouse/metrics.yml.
select
    customer_key,
    sum(order_amt) as order_amt_sum_1d,
    count(*) as order_cnt_1d,
    sum(order_amt) filter (where channel = 'app') as app_order_amt_sum_1d,
    date '{{ get_dt() }}' as dt
from {{ ref('dwd_trade_order_di') }}
where dt = date '{{ get_dt() }}'
group by customer_key
