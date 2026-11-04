# Scenario: dimension-attribute-history

skills: dwh-start, dwh-model-design, dwh-implement

## Prompt

Add customer segment to the finance dashboard. Segments change every month and finance wants revenue by the segment the customer had when they ordered.

## Pass if

- It classifies the change as reuse (a new attribute on the existing `customer` dimension) and follows
  dwh-model-design.
- It marks `segment` `history: historical` on `customer` in `warehouse/dimensions.yml`.
- It resolves the segment in DWD (`dwd_trade_order_di`) with a point-in-time join to `dim_pub_customer_hist`
  (STD-05-05), as `customer_city` already is.

## Fail if

- It adds segment as a current attribute read from `dim_pub_customer` at query time.
