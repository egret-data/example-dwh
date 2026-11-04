# Scenario: scaffold-dws

skills: dwh-start, dwh-model-design, dwh-implement

## Prompt

Create a DWS with the 7-day order amount per shop.

## Pass if

- It checks `warehouse/metrics.yml` (and finds no shop-grain derived metric over `order_amt`).
- It declares a derived metric over `order_amt` with grain `shop` (`order_amt_sum_1w` with period `1w`, or nd
  with `days: 7`).
- It uses `dwh scaffold dws_trade_shop_<period> --metric ...` to start the model.
- It applies STD-07-04 (names two consumers or performance evidence for the DWS).

## Fail if

- It hand-writes DWS SQL with an undeclared metric column.
