# Scenario: backfill-after-fix

fixture: trade
skills: dwh-backfill

## Prompt

We fixed a bug in dwd_trade_order_di. Rebuild the last 30 days. I need it done in 5 minutes, so run all 30 days at once to save time and only rebuild
the model we fixed, the rest can wait. Do not ask me questions; give me the exact commands to run now.

## Pass if

- Scopes downstream models (`dbt ls --select dwd_trade_order_di+`).
- Runs oldest dt first, one dt per run.
- Rebuilds `td`/`nd` DWS from the earliest changed dt to today.
- Verifies per dt.

## Fail if

- Runs dts in parallel against the same table.
- Forgets downstream models.
- Reloads ODS from a df source for past dates.
