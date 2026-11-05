# Scenario: dimension-attribute-history

skills: dwh-start, dwh-requirement, dwh-model-design

## Prompt

Add customer segment to the finance dashboard. Segments change every month and finance wants revenue by the segment the customer had when they ordered.

## Pass if

- It finds that `segment` is not in the source (`ods_shop_customers_df` has no such column) and classifies the
  change as model-extending: a new source column plus a new attribute on the existing `customer` dimension, which
  needs a design record and `design-approved` before SQL.
- It plans `segment` as a historical attribute of `customer` (`history: historical` in `warehouse/dimensions.yml`,
  kept in `dim_pub_customer_hist`). A requirement-stage answer that writes no YAML meets this when it names that as
  the planned design.
- It plans a point-in-time join from the order to `dim_pub_customer_hist` (STD-05-05), resolved in DWD
  (`dwd_trade_order_di`) as `customer_city` already is, so revenue uses the segment the customer had when ordering.
  A requirement-stage answer meets this when it names that join as the planned design; it may still ask how and
  when the source records a segment change.

## Fail if

- It adds segment as a current attribute read from `dim_pub_customer` at query time.
- It proposes reading `segment` from `dim_pub_customer` (the current state), or from `dim_pub_customer_hist`
  filtered to the current version, for revenue by the segment at order time.
- It treats current versus order-time segment as an open question for finance; the request already says order
  time.
