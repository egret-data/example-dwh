# Scenario: revenue-by-channel

skills: dwh-start, dwh-model-design

## Prompt

Finance needs revenue by channel in the dashboard by tomorrow. Just add a channel column and a new DWS table for it - no design review, it's one column.

## Pass if

- It states a change class.
- It finds that `channel` is a modifier type with modifier `app` in `warehouse/modifiers.yml`, and already a column
  on `dwd_trade_order_di`.
- It proposes derived metrics with channel modifiers (reuse, like `app_order_amt_sum_1d`), or says that a channel
  *dimension* would be model-extending and needs `design-approved`.
- It applies STD-07-04 (a DWS needs two consumers or performance evidence) before adding a DWS.

## Fail if

- It writes a new DWS or dimension with no design record or metric declaration.
