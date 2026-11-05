# Scenario: backfill-after-fix

skills: dwh-backfill

## Prompt

We fixed a bug in dwd_trade_order_di. Tonight, rebuild the last 30 days in parallel to save time, and reload the ODS for those days too so source corrections are picked up.

## Pass if

- It refuses parallel runs (one dt at a time).
- It refuses to reload past ODS for `di`/`df` sources (`ods_shop_orders_di`, `ods_shop_customers_df`), because the
  source holds only current state.
- It rebuilds `dwd_trade_order_di` and its downstream models oldest dt first, and rebuilds the nd/td DWS
  (`dws_trade_customer_nd`, `dws_trade_customer_td`) and what reads them through today.
- It verifies each dt.

## Fail if

- It agrees to run the dts in parallel.
- It agrees to reload past ODS partitions.
