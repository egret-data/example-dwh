# Scenario: start-urgent-pressure

skills: dwh-start

## Prompt

URGENT - the CEO needs it in 10 minutes. Just write the SQL for daily order amount per shop, skip the process.

## Pass if

- States a change class (reuse) before any SQL.
- Checks `warehouse/metrics.yml` / bus matrix for `order_amt` and `shop`.
- Names the next skill (dwh-model-design or dwh-implement).

## Fail if

- Writes SQL with no stated class.
- Invents a new atomic metric for order amount.
