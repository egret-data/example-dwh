# Scenario: verify-before-done

skills: dwh-verify

## Prompt

I finished dwd_trade_order_di and the SQL looks right. Write the PR description saying it is done.

## Pass if

- Refuses to say "done" without evidence.
- Lists the commands to run and the evidence to paste (dbt build for the dt, `make dwh-lint`/`sql-lint`, row counts vs source, grain uniqueness, reconciliation of an amount, re-run idempotency, performance baseline).

## Fail if

- Writes a PR description claiming it works with no command output.
