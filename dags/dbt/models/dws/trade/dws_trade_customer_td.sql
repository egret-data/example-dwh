{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

-- One statistical period per table (td); metric columns follow warehouse/metrics.yml.
select
    customer_key,
    sum(order_amt) as order_amt_sum_td,
    count(*) as order_cnt_td,
    date '{{ get_dt() }}' as dt
from {{ ref('dwd_trade_order_di') }}
where dt <= date '{{ get_dt() }}'
group by customer_key
