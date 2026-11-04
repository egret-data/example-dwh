# 12 — Data quality and verification

Scope: test severity, source freshness, reconciliation and performance evidence. The tests every model needs are in
STD-09-02; this file covers how they are judged and what a change must record. The skill `dwh-verify` runs the
checks.

Differences from Alibaba:

- Alibaba's result validation compares performance before and after an optimization. It does not check data
  correctness. STD-12-03 adds the correctness checks (row counts and amounts between layers); STD-12-05 keeps the
  performance comparison.

## Rules

### STD-12-01 Severities (MUST)

A test with `severity: error` blocks the build. That is the default, and the right level for grain, `not_null` and
`relationships` tests. Use `severity: warn` only for a known, monitored issue, and put the ticket in the description
of the column or model so the warning has an owner and an end date.

Correct:

```yaml
columns:
  - name: city
    description: City of the default address. Known gaps are tracked in DWH-142.
    data_tests:
      - not_null:
          config:
            severity: warn
```

Incorrect:

```yaml
columns:
  - name: city
    description: City of the default address.   # a warn test with no ticket: nobody owns the warning
    data_tests:
      - not_null:
          config:
            severity: warn
```

Source: Spec §7

### STD-12-02 Source freshness (SHOULD)

Each source table that has a watermark sets `loaded_at_field` and a freshness threshold, so a stalled source is seen
before a model builds on old data. A watermark that holds naive local time is converted to an instant first, as
`source_ts()` does in models, because dbt compares the field with the current UTC time.

Correct:

```yaml
sources:
  - name: shop
    tables:
      - name: orders
        config:
          loaded_at_field: "with_timezone(cast(updated_at as timestamp(6)), 'Asia/Ho_Chi_Minh')"
          freshness:
            warn_after: {count: 26, period: hour}
            error_after: {count: 50, period: hour}
```

Incorrect:

```yaml
sources:
  - name: shop
    tables:
      - name: orders   # meta.watermark is updated_at, but no loaded_at_field or freshness
        config:
          meta:
            watermark: updated_at
```

Source: Spec §7

### STD-12-03 Reconciliation (MUST)

For each changed dt, compare ODS and DWD row counts and one amount, and compare DWD and DWS totals. The numbers
match, or the difference is explained by a documented filter. Record the numbers in the change description. Exact
functions only: approximate ones are for ADS (STD-10-06).

Correct:

```sql
select
    (select count(*) from ods.ods_shop_orders_di where dt = date '2026-11-02') as ods_rows,
    (select count(*) from dwd.dwd_trade_order_di where dt = date '2026-11-02') as dwd_rows,
    (select sum(total_amount) from ods.ods_shop_orders_di where dt = date '2026-11-02') as ods_amt,
    (select sum(order_amt) from dwd.dwd_trade_order_di where dt = date '2026-11-02') as dwd_amt
```

Incorrect:

```sql
select
    (select count(*) from ods.ods_shop_orders_di) as ods_rows,    -- not for the changed dt
    (select count(*) from dwd.dwd_trade_order_di) as dwd_rows
```

Source: Spec §7

### STD-12-04 Inferred members (SHOULD)

Count the inferred members of each DIM per dt (STD-04-07) and alert when the count grows. A few are normal: they
are facts that arrived before their dimension row. A rising count means the dimension load is late or the source key
is wrong.

Correct:

```sql
select dt, count(*) as inferred_member_cnt
from dim.dim_pub_customer
where is_inferred
group by dt
order by dt desc
```

Incorrect:

```text
inferred members are created and never counted   # nobody sees a dimension load that is falling behind
```

Source: Kimball (late-arriving dimensions) · Spec §7

### STD-12-05 Performance baseline (MUST)

For every change to an existing model, record before and after: wall time, input rows and bytes, output rows, and
the Iceberg file count and size. Take the "before" numbers on the unchanged model, and compare after the change. A
new model records its first numbers as the baseline.

Correct:

```sql
select count(*) as file_cnt, sum(file_size_in_bytes) as bytes, sum(record_count) as rows_cnt
from ods."ods_shop_orders_di$files"
```

Incorrect:

```text
"The model is faster now."   # no wall time, no rows, no bytes, no before
```

Source: Alibaba performance-benchmark-establishment · Alibaba result-verification
