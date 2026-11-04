# Scenario: reuse-derived-metric

fixture: trade
skills: dwh-start, dwh-model-design

## Prompt

Add the 7-day order amount per customer for the BI dashboard. I'm in a hurry (5 minutes) and I already wrote the SQL and the YAML for a new metric called customer_7d_order_value, just check it is fine.

## Pass if

- Classifies as reuse.
- Reuses atomic `order_amt`.
- Proposes one derived metric named by the template (`order_amt_sum_1w` with period `1w`, or `order_amt_sum_7d` with period `nd` and `days: 7`).
- Notes BI can read DWD+DIM or a DWS only if justified.

## Fail if

- Proposes a new atomic metric, process or DWD.
- Names the metric outside the template.
