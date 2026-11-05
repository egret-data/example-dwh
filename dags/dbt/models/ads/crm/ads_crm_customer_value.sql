{{ config(materialized='table') }}

-- Serves one application need: name its consumer in the .yml description (docs/standards/07-dws-ads.md).
select
    customer_key,
    order_amt_sum_td,
    order_cnt_td,
    order_amt_sum_td / nullif(order_cnt_td, 0) as avg_order_amt_td,
    dt
from {{ ref('dws_trade_customer_td') }}
