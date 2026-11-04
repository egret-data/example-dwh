# 07 — Summary (DWS) and application (ADS) tables

Scope: when to build DWS and ADS tables, and their shape. A DWS aggregates DWD and DIM data along common dimensions
for one statistical period. An ADS serves one application. Metric definitions are in file 06.

## Rules

### STD-07-01 Declared grain (MUST)

A DWS sets `config.meta.grain` to its grain columns. Every column of the table is a grain column, `dt` or a metric.
DWH-M03 reports a missing grain and any other column. The grain columns are keys of conformed dimensions, so they
carry the `relationships` test of DWH-T04.

Correct:

```yaml
models:
  - name: dws_trade_customer_1d
    config:
      meta:
        grain: [customer_key]
    columns:
      - name: customer_key
      - name: order_amt_sum_1d
        config:
          meta: {metric: order_amt_sum_1d}
      - name: dt
```

Incorrect:

```yaml
models:
  - name: dws_trade_customer_1d
    config:
      meta:
        grain: [customer_key]
    columns:
      - name: customer_key
      - name: customer_city     # neither a grain column, dt, nor a metric
      - name: order_amt_sum_1d
        config:
          meta: {metric: order_amt_sum_1d}
      - name: dt
```

Source: Alibaba data-warehouse-service-layer
Checked by: DWH-M03

### STD-07-02 One period per DWS table (MUST)

All metric columns of a DWS share the table's period, which is the period token at the end of its name. Batch DWS
tables default to the `1d`, `nd` and `td` triple; split an `nd` table only by one period (for example `1w`). DWH-M05
compares each metric's period with the table name.

Correct:

```yaml
models:
  - name: dws_trade_customer_nd
    columns:
      - name: app_order_amt_sum_30d
        config:
          meta: {metric: app_order_amt_sum_30d}   # period nd
```

Incorrect:

```yaml
models:
  - name: dws_trade_customer_1d
    columns:
      - name: app_order_amt_sum_30d               # period nd inside a 1d table
        config:
          meta: {metric: app_order_amt_sum_30d}
```

Source: Alibaba data-warehouse-service-layer
Checked by: DWH-M05

### STD-07-03 Metric columns are declared metrics (MUST)

Every DWS metric column sets `config.meta.metric` to a derived metric of `metrics.yml` and is named exactly like it.
The same holds for an ADS column that declares a metric, which may also be a calculated one. DWH-M03 reports a DWS
column with no metric; DWH-M04 reports an unknown metric and a column named otherwise.

Correct:

```sql
select
    customer_key,
    sum(order_amt) as order_amt_sum_1d,
    count(*) as order_cnt_1d,
    date '{{ get_dt() }}' as dt
from {{ ref('dwd_trade_order_di') }}
where dt = date '{{ get_dt() }}'
group by customer_key
```

Incorrect:

```sql
select
    customer_key,
    sum(order_amt) as order_amt,   -- the column declares meta.metric order_amt_sum_1d; the name must match
    date '{{ get_dt() }}' as dt
from {{ ref('dwd_trade_order_di') }}
where dt = date '{{ get_dt() }}'
group by customer_key
```

Source: Spec §8.1
Checked by: DWH-M03, DWH-M04

### STD-07-04 Build DWS only when it pays (MUST)

Build a DWS only with at least two consumers or recorded performance evidence, such as the baseline that
`dwh-verify` records. Otherwise consumers read DWD and DIM. State the reason in the model description. No lint code
checks this; the design gate reviews it.

Correct:

```yaml
models:
  - name: dws_trade_customer_1d
    description: >
      Daily order metrics per customer. Consumers: ads_finance_customer_order_1d and the sales dashboard.
```

Incorrect:

```yaml
models:
  - name: dws_trade_customer_1d
    description: Daily order metrics per customer.   # no second consumer, no baseline
```

Source: Spec §7

### STD-07-05 ADS names its consumer (MUST)

An ADS serves one application need. Its description names the consumer and the need, so a later change knows who it
affects. No lint code checks this; the design gate reviews it.

Correct:

```yaml
models:
  - name: ads_finance_customer_order_1d
    description: Daily order amount per customer for the finance dashboard "Revenue by customer".
```

Incorrect:

```yaml
models:
  - name: ads_finance_customer_order_1d
    description: Order data for customers.   # no consumer, no need
```

Source: Spec §7

### STD-07-06 No stored calculated metrics below ADS (MUST)

Calculated metrics are not stored in DWD or DWS. Store their inputs there and compute the ratio in ADS or in BI.
DWH-M06 reports a DWD or DWS column whose `meta.metric` is a calculated metric.

Correct:

```sql
-- ads_finance_customer_order_1d
select
    customer_key,
    order_amt_sum_1d / nullif(order_cnt_1d, 0) as avg_order_amt_1d,
    dt
from {{ ref('dws_trade_customer_1d') }}
where dt = date '{{ get_dt() }}'
```

Incorrect:

```yaml
models:
  - name: dws_trade_customer_1d
    columns:
      - name: avg_order_amt_1d  # a calculated metric stored in a DWS
        config:
          meta: {metric: avg_order_amt_1d}
```

Source: Spec §5
Checked by: DWH-M06
