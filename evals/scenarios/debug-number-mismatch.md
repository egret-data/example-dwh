# Scenario: debug-number-mismatch

skills: dwh-debug

## Prompt

Yesterday's order amount in the dashboard is 5% lower than in the shop database. Fix it quickly.

## Pass if

- Reproduces for an exact dt.
- Traces lineage down layer by layer comparing counts/amounts (DWS/ADS -> `dwd_trade_order_di` ->
  `ods_shop_orders_di` -> source).
- Names likely causes (Vietnam-day window vs source timezone, late-arriving rows, deletes, join fan-out).
- Writes a failing test before fixing at the lowest wrong layer.

## Fail if

- Patches the dashboard/ADS number.
- Proposes a fix before locating the layer.
