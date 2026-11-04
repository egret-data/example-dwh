# 05 — Facts

Scope: DWD fact tables. A fact table holds the atomic records of one business process. The rules cover fact types,
grain, measures, additivity and the way a fact reads dimensions.

Differences from Alibaba:

- Alibaba calls copying dimension attributes onto a fact "degenerating". Here that is *dimension denormalization*
  (STD-05-07).
- *Degenerate dimension* keeps Kimball's meaning: a transaction identifier kept on the fact (STD-04-10).

## Rules

### STD-05-01 Fact type per process (MUST)

Each DWD loads one process and follows its fact type: transaction, periodic snapshot or accumulating snapshot. The
type is declared once, in `processes.yml`, and the schema (DWH-Y01) rejects any other value. The DWD names the process
in `config.meta.process` (DWH-B01). An accumulating snapshot reads the transaction facts of its process, not ODS.

Correct:

```yaml
processes:
  - name: shipment
    domain: trade
    description: An order moves from placed to delivered.
    fact_type: accumulating_snapshot
    grain: One row per order, updated at each milestone.
```

Incorrect:

```yaml
processes:
  - name: shipment
    domain: trade
    description: An order moves from placed to delivered.
    fact_type: snapshot         # not one of transaction, periodic_snapshot, accumulating_snapshot
    grain: One row per order, updated at each milestone.
```

Source: Kimball (fact table types) · Alibaba data-warehouse-detail-layer
Checked by: DWH-Y01, DWH-B01

### STD-05-02 One grain per table (MUST)

A fact table has one grain. The grain is encoded as its uniqueness test over the grain columns plus `dt`, and each
grain column has a `not_null` test. The checks (DWH-T01, DWH-T02) find a missing uniqueness test and a grain column
without `not_null`. They cannot tell whether the grain columns are the right ones.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    columns:
      - name: order_id
        data_tests: [not_null]
      - name: dt
        data_tests: [not_null]
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns: [order_id, dt]
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di
    columns:
      - name: order_id          # grain column without not_null
      - name: dt
        data_tests: [not_null]
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns: [order_id, dt]
```

Source: Kimball (grain) · Alibaba data-warehouse-detail-layer
Checked by: DWH-T01, DWH-T02

### STD-05-03 Units and nulls (MUST)

All measures of a process use the same unit in every table. The null policy of each measure is written in its column
description: zero, null or a sentinel, decided once. No lint code checks this; the description checks (DWH-D01, DWH-D02)
only require that a description exists.

Correct:

```yaml
columns:
  - name: order_amt
    description: Order amount in VND, tax included. Never null; 0 for a free order.
    data_type: decimal(38, 4)
```

Incorrect:

```yaml
# dwd_trade_order_di.yml
columns:
  - name: order_amt
    description: Order amount in VND, tax included. Never null; 0 for a free order.
# dwd_trade_order_item_di.yml
columns:
  - name: order_amt
    description: Order amount in USD.   # same measure, different unit, no null policy
```

Source: Alibaba data-warehouse-detail-layer

### STD-05-04 Additivity (MUST)

Declare each atomic metric as additive, semi-additive or non-additive. A semi-additive metric names the dimension
it cannot be summed across; the schema requires it. DWH-M02 rejects a derived metric on a non-additive atomic
metric, and DWH-M06 rejects a calculated metric stored in DWD or DWS. Store the numerator and the denominator,
never the ratio.

Correct:

```yaml
atomic:
  - name: balance_amt
    process: balance
    description: Account balance at day end.
    aggregation: sum
    additivity: semi_additive
    non_additive_dimension: date
```

Incorrect:

```yaml
atomic:
  - name: balance_amt
    process: balance
    description: Account balance at day end.
    aggregation: sum
    additivity: semi_additive   # no non_additive_dimension
```

Source: Kimball (additive, semi-additive, non-additive facts) · Spec §5
Checked by: DWH-M02, DWH-M06

### STD-05-05 Point-in-time joins for historical attributes (MUST)

A `historical` attribute is resolved in DWD by joining `dim_*_hist` on the durable key with
`event_at >= valid_from and (event_at < valid_to or valid_to is null)`, and the value is stored on the fact. A
`current` attribute is not copied; it is read from `dim_*` at query time. Compare `event_at` with the snapshot
columns in the same time zone. No lint code checks this yet.

Correct:

```sql
select
    o.order_id,
    c.city as customer_city
from {{ ref('ods_shop_orders_di') }} as o
left join {{ ref('dim_pub_customer_hist') }} as c
    on c.customer_key = {{ dbt_utils.generate_surrogate_key(['o.customer_id']) }}
    and o.created_at >= c.valid_from
    and (o.created_at < c.valid_to or c.valid_to is null)
where o.dt = date '{{ get_dt() }}'
```

Incorrect:

```sql
select
    o.order_id,
    c.city as customer_city
from {{ ref('ods_shop_orders_di') }} as o
left join {{ ref('dim_pub_customer_hist') }} as c
    on c.customer_key = {{ dbt_utils.generate_surrogate_key(['o.customer_id']) }}   -- no time condition: one row per version
where o.dt = date '{{ get_dt() }}'
```

Source: Kimball (type 4 history lookup) · Spec §2

### STD-05-06 Facts carry durable keys (MUST)

Each dimension a fact uses appears as a `_key` column with a `relationships` test to its DIM. DWH-T04 finds a key
column without the test, and DWH-B04 finds a key whose dimension is not in the process's row of the bus matrix.

Correct:

```yaml
columns:
  - name: customer_key
    data_type: varchar
    data_tests:
      - relationships:
          arguments:
            to: ref('dim_pub_customer')
            field: customer_key
```

Incorrect:

```yaml
columns:
  - name: customer_key          # no relationships test to dim_pub_customer
    data_type: varchar
```

Source: Kimball (surrogate keys in facts) · Spec §7
Checked by: DWH-T04, DWH-B04

### STD-05-07 Dimension denormalization (SHOULD)

Frequently filtered current attributes may be copied onto the DWD to save joins. Name the copy after the attribute and
keep the `_key` column, so the fact still joins to the dimension. A `historical` attribute stored on the fact follows
STD-05-05 instead.

Correct:

```sql
select
    order_id,
    shop_key,
    shop_name           -- copied from dim_trade_shop, key kept
from ...
```

Incorrect:

```sql
select
    order_id,
    shop_name           -- shop_key dropped: the fact can no longer join to the dimension
from ...
```

Source: Alibaba data-warehouse-detail-layer
