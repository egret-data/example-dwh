# 10 — Trino SQL style

Scope: the SQL in dbt models. `make sql-lint` runs sqlfluff with the Trino dialect over `dags/dbt/models`, using the
root `.sqlfluff` and the per-layer overrides in `models/ods` and `models/dws`. It checks layout; the rules below
that no tool checks are reviewed.

## Rules

### STD-10-01 sqlfluff clean (MUST)

Every model passes `make sql-lint`: lowercase keywords, aliases aligned in the select list, a line length of 110.
Run `make sql-fix`, which runs `sqlfluff fix` over the models, rather than hand-formatting. The DWS folder relaxes
alias alignment because aggregate expressions are too wide to align.

Correct:

```sql
select
    order_id,
    customer_id,
    cast(total_amount as decimal(18, 2)) as total_amount,
    date '{{ get_dt() }}'                as dt
from {{ ref('ods_shop_orders_di') }}
```

Incorrect:

```sql
SELECT   -- uppercase keywords
    order_id,
    customer_id,
    cast(total_amount as decimal(18, 2)) as total_amount,
    date '{{ get_dt() }}'                as dt
FROM {{ ref('ods_shop_orders_di') }}
```

Source: Spec §7

### STD-10-02 CTEs over nested subqueries (SHOULD)

Name each step as a CTE with one purpose, and end the model with a final `select` from the last CTE. Read the CTEs
top to bottom like a pipeline. A nested subquery hides a step that deserves a name and a place to test it.

Correct:

```sql
with orders as (
    select order_id, customer_id, total_amount
    from {{ ref('ods_shop_orders_di') }}
    where dt = date '{{ get_dt() }}'
),

per_customer as (
    select customer_id, sum(total_amount) as order_amt_sum_1d
    from orders
    group by customer_id
)

select customer_id, order_amt_sum_1d
from per_customer
```

Incorrect:

```sql
select customer_id, order_amt_sum_1d   -- the first step is buried in a subquery
from (
    select customer_id, sum(total_amount) as order_amt_sum_1d
    from {{ ref('ods_shop_orders_di') }}
    where dt = date '{{ get_dt() }}'
    group by customer_id
) as per_customer
```

Source: Spec §7

### STD-10-03 No select star outside ODS (MUST)

List the columns outside ODS. The sqlfluff rule AM04 reports `select *` and runs for every folder except
`models/ods`, which mirrors source tables. An explicit list keeps a new upstream column out of a contract and out of
a downstream table by accident.

Correct:

```sql
select
    order_id,
    customer_id,
    dt
from {{ ref('ods_shop_orders_di') }}
```

Incorrect:

```sql
select *   -- a DWD must list its columns
from {{ ref('ods_shop_orders_di') }}
```

Source: Spec §7

### STD-10-04 Filter partitions early (MUST)

Filter on `dt` in the CTE that reads a partitioned table, so Iceberg prunes partitions before any join or
aggregation. Trino may push a later filter down to the scan, but then pruning depends on the optimizer, and the filter
sits far from the read it protects. Dimension reads follow their own shape (file 04).

Correct:

```sql
with orders as (
    select order_id, customer_id, total_amount
    from {{ ref('ods_shop_orders_di') }}
    where dt = date '{{ get_dt() }}'
)

select order_id, customer_id, total_amount
from orders
```

Incorrect:

```sql
with orders as (
    select order_id, customer_id, total_amount, dt
    from {{ ref('ods_shop_orders_di') }}   -- no dt filter next to the read; pruning depends on the optimizer
)

select order_id, customer_id, total_amount
from orders
where dt = date '{{ get_dt() }}'
```

Source: Alibaba data-warehouse-performance-optimization · Spec §7

### STD-10-05 Check join fan-out (MUST)

Join on the full key of the other side, so each left row matches at most one right row. After a join, the model's
grain test must still pass; a fan-out shows up there first. Join a fact to a DIM on the durable key the fact
already carries, not on a natural id. Joining a fact to a `dim_*_hist` snapshot needs the time condition of file 05,
or one fact row becomes one row per version.

Correct:

```sql
select
    o.order_id,
    c.city
from {{ ref('dwd_trade_order_di') }} as o
left join {{ ref('dim_pub_customer') }} as c
    on c.customer_key = o.customer_key   -- the durable key: one current row per key
```

Incorrect:

```sql
select
    o.order_id,
    p.payment_id
from orders as o
left join payments as p
    on p.customer_id = o.customer_id   -- not the order key: one order matches every payment of the customer
```

Source: Kimball (grain) · Spec §7

### STD-10-06 Approximate functions only in ADS (MUST)

`approx_distinct`, `approx_percentile` and other approximate functions appear only in ADS. A DWS metric is
re-aggregated and compared in reconciliation (STD-12-03), and an approximate value breaks both. An ADS may trade
exactness for speed because nothing builds on it. An ADS reads a DWS, or sets `config.meta.dwd_reason` (STD-01-04).

Correct:

```sql
-- ads_finance_customer_active_1d
select
    dt,
    approx_distinct(customer_key) as active_customer_cnt_1d
from {{ ref('dws_trade_customer_1d') }}
group by dt
```

Incorrect:

```sql
-- dws_trade_customer_1d
select
    customer_key,
    approx_distinct(order_id) as order_cnt_1d,   -- approximate value in a DWS
    dt
from {{ ref('dwd_trade_order_di') }}
group by customer_key, dt
```

Source: Spec §7
