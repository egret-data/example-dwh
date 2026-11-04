# 06 — Metrics

Scope: atomic, derived and calculated metrics, and the modifiers that narrow them. The source of truth is
`warehouse/metrics.yml` and `warehouse/modifiers.yml`. The rules apply to the design files and to the metric columns
that DWS and ADS tables take from them (file 07).

Differences from Alibaba: calculated metrics are a Kimball-style extension. Alibaba defines only atomic and derived
metrics.

## Rules

### STD-06-01 Atomic metrics (MUST)

An atomic metric is a process, a measure and an aggregation (`sum`, `count`, `count_distinct`, `min` or `max`), plus
its additivity. It has no period and no filter. The schema (DWH-Y01) rejects any other aggregation, and DWH-Y03
rejects an unknown process.

Correct:

```yaml
atomic:
  - name: order_amt
    process: order
    description: Order amount.
    aggregation: sum
    additivity: additive
```

Incorrect:

```yaml
atomic:
  - name: order_amt
    process: order
    description: Order amount.
    aggregation: avg            # not an aggregation; an average is a calculated metric
    additivity: additive
```

Source: Alibaba specify-statistical-metrics
Checked by: DWH-Y01, DWH-Y03

### STD-06-02 Derived metrics (MUST)

A derived metric is an atomic metric, one period, optional modifiers and a grain of conformed dimensions. Each grain
entry is a dimension from `dimensions.yml`, not a column name. DWH-Y03 rejects an unknown atomic metric, period,
modifier or dimension.

Correct:

```yaml
derived:
  - name: order_amt_sum_1d
    atomic: order_amt
    period: 1d
    grain: [customer]
    description: Order amount per customer per day.
```

Incorrect:

```yaml
derived:
  - name: order_amt_sum_1d
    atomic: order_amt
    period: 1d
    grain: [customer_id]        # a column, not a dimension of dimensions.yml
    description: Order amount per customer per day.
```

Source: Alibaba specify-statistical-metrics
Checked by: DWH-Y03

### STD-06-03 Calculated metrics for ratios (MUST)

Ratios, averages and other non-additive results are calculated metrics over stored derived metrics. A derived metric
on a non-additive atomic metric is an error (DWH-M02). Store the numerator and the denominator as derived metrics,
and write the formula as a calculated metric. Trino raises an error on division by zero, so every calculated
division uses `nullif` on the denominator.

Correct:

```yaml
calculated:
  - name: avg_order_amt_1d
    formula: order_amt_sum_1d / nullif(order_cnt_1d, 0)
    inputs: [order_amt_sum_1d, order_cnt_1d]
    description: Average order amount per customer per day.
```

Incorrect:

```yaml
atomic:
  - name: avg_order_amt
    process: order
    description: Average order amount.
    aggregation: sum
    additivity: non_additive
derived:
  - name: avg_order_amt_sum_1d  # a derived metric over a non-additive atomic metric
    atomic: avg_order_amt
    period: 1d
    grain: [customer]
    description: Average order amount per customer per day.
```

Source: Kimball (non-additive facts) · Spec §5
Checked by: DWH-M02

### STD-06-04 Metric names (MUST)

Derived metric names follow `{modifiers}_{atomic}_{agg}_{period}`. The aggregation token is `sum`, `cnt`, `dcnt`,
`min` or `max`. An `nd` period is written as the number of days plus `d`. Modifiers come first, in the order listed
in the metric.

Correct:

```yaml
derived:
  - name: app_order_amt_sum_30d
    atomic: order_amt
    period: nd
    days: 30
    modifiers: [app]
    grain: [customer]
    description: App order amount per customer, last 30 days.
```

Incorrect:

```yaml
derived:
  - name: order_amt_app_sum_30d # modifier after the atomic metric
    atomic: order_amt
    period: nd
    days: 30
    modifiers: [app]
    grain: [customer]
    description: App order amount per customer, last 30 days.
```

Source: Spec §7
Checked by: DWH-M01

### STD-06-05 Typed modifiers (MUST)

A modifier has a type, a predicate and the processes it applies to. It inherits its domain from its type, so it is
declared once and reused. DWH-Y03 rejects a modifier whose type or process does not exist.

Correct:

```yaml
modifier_types:
  - {name: channel, domain: trade, description: Sales channel.}
modifiers:
  - name: app
    type: channel
    predicate: "channel = 'app'"
    processes: [order]
    description: Orders placed in the mobile app.
```

Incorrect:

```yaml
modifier_types:
  - {name: channel, domain: trade, description: Sales channel.}
modifiers:
  - name: app
    type: channel
    predicate: "channel = 'app'"
    processes: [orders]         # the process is called order
    description: Orders placed in the mobile app.
```

Source: Alibaba specify-statistical-metrics
Checked by: DWH-Y03

### STD-06-06 nd periods fix their length (MUST)

A derived metric with period `nd` sets `days`, and no other period sets it. Without `days`, `nd` does not say how
many days it covers. The schema (DWH-Y01) enforces both directions and requires at least 2 days.

Correct:

```yaml
derived:
  - name: order_amt_sum_7d
    atomic: order_amt
    period: nd
    days: 7
    grain: [customer]
    description: Order amount per customer, last 7 days.
```

Incorrect:

```yaml
derived:
  - name: order_amt_sum_1d
    atomic: order_amt
    period: 1d
    days: 7                     # only nd sets days
    grain: [customer]
    description: Order amount per customer per day.
```

Source: Alibaba data-warehouse-service-layer · Spec §5
Checked by: DWH-Y01
