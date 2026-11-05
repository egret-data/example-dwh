# Scenario: review-bad-model

skills: dwh-review

## Prompt

Review this new model before I merge it:

`models/dwd/trade/dwd_trade_return_di.sql`

```sql
select * from {{ ref('ods_shop_orders_di') }} o join {{ ref('dim_pub_customer') }} c on o.customer_id = c.customer_id
```

Its .yml has no tests.

## Pass if

- Flags `select *` outside ODS.
- Flags the join on a natural id instead of the durable key / fan-out risk.
- Flags missing grain, not_null and relationships tests and contract.
- Flags missing `meta.process`.
- Flags that the process `return` is not in `processes.yml`.
- Ranks issues by severity.

## Fail if

- Approves it.
- Lists only style nits.
