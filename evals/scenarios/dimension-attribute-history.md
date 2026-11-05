# Scenario: dimension-attribute-history

skills: dwh-start, dwh-requirement, dwh-model-design

## Prompt

Add customer segment to the finance dashboard. Segments change every month and finance wants revenue by the segment the customer had when they ordered.

## Pass if

- It finds that `segment` is not in the source (`ods_shop_customers_df` has no such column) and classifies the
  change as model-extending: a new source column plus a new attribute on the existing `customer` dimension, which
  needs a design record and `design-approved` before SQL.
- It treats `segment` as a historical attribute of `customer`: it plans `history: historical` for `segment` in
  `warehouse/dimensions.yml` (or names the order-time segment as an SCD history requirement in its design record),
  or, stopping at requirement questions as `dwh-requirement` does, it asks the question that decides the history
  design (for example how and when the source records a segment change).
- It names a point-in-time join to the customer history (`dim_pub_customer_hist`, STD-05-05) as the planned way to
  get the segment the customer had at order time, resolved in DWD as `customer_city` already is; or, at the
  requirement stage, it asks the question that decides that join (for example which timestamp marks a segment
  change). A requirement-stage answer need not write the YAML or the SQL to meet this.

## Fail if

- It adds segment as a current attribute read from `dim_pub_customer` at query time.
