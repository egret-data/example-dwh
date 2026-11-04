# 01 — Layers and dependencies

Scope: the five layers (ODS, DIM, DWD, DWS, ADS), what each one holds and which layer may read which. The rules apply
to every dbt model and snapshot.

Differences from Alibaba: Alibaba groups DIM, DWD and DWS into one common data model layer (CDM). Here they are three
folders with their own name prefixes. In Alibaba, ADS reads the CDM, DWD included, and must not read ODS directly.
Here ADS must not read ODS either, and it reads DWS and DIM; it may read DWD only when its `.yml` gives a
`dwd_reason` (STD-01-04).

## Rules

### STD-01-01 Five layers, one folder each (MUST)

Models live in `models/<ods|dim|dwd|dws|ads>/`. Snapshots are DIM history: the checker treats every snapshot as a DIM
object and names it `dim_..._hist`. The name prefix equals the layer: a model in `models/dwd/` is named `dwd_...`.

Correct:

```text
models/dwd/trade/dwd_trade_order_di.sql
models/dim/dim_pub_date.sql
```

Incorrect:

```text
models/staging/dwd_trade_order_di.sql        # not under a layer folder
models/dws/dwd_trade_order_di.sql            # prefix dwd_ in the dws folder
```

Source: Alibaba divide-a-data-warehouse-into-layers · Spec §3
Checked by: DWH-L01, DWH-L02

### STD-01-02 Only ODS reads sources (MUST)

`source()` appears only in ODS models. An ODS model reads exactly the source it mirrors and no other model: it has a
`source()` and no `ref()`. Every later layer starts from ODS, so a change in a source is absorbed in one place.

Correct:

```sql
-- models/ods/shop/ods_shop_orders_di.sql
select * from {{ source('shop', 'orders') }}
```

Incorrect:

```sql
-- models/dwd/trade/dwd_trade_order_di.sql
-- source() outside ODS
select * from {{ source('shop', 'orders') }}
```

Source: Alibaba specify-the-principles-for-using-data-at-different-layers · Spec §7
Checked by: DWH-L03

### STD-01-03 Dependencies point down (MUST)

DIM and DWD read ODS and DIM. DWS reads DWD, DIM and coarser-grain DWS. ADS reads DWS and DIM. Snapshots read ODS or
the current DIM model. No model reads a layer above it, and no model reads its own layer except where listed (DIM,
DWS), and except an accumulating-snapshot DWD, which reads the transaction DWDs of its process (STD-01-05). ADS
reading DWD with a reason is STD-01-04. The checker compares the layer of each `ref()` target with this list.

Correct:

```sql
-- models/dws/trade/dws_trade_customer_1d.sql
select customer_key, sum(pay_amt) as pay_amt_sum_1d, date '{{ get_dt() }}' as dt
from {{ ref('dwd_trade_payment_di') }}
where dt = date '{{ get_dt() }}'
group by customer_key
```

Incorrect:

```sql
-- models/dwd/trade/dwd_trade_payment_di.sql
-- DWD reads DWS: an upward read
select * from {{ ref('dws_trade_customer_1d') }}
```

Source: Alibaba specify-the-principles-for-using-data-at-different-layers · Spec §7
Checked by: DWH-L04

### STD-01-04 ADS reads DWD only with a reason (MUST)

An ADS model may read DWD only when its `.yml` sets `config.meta.dwd_reason`, a sentence saying why no DWS serves the
need. Without it, build or reuse a DWS. The checker tests that the key is present and non-empty, not that the reason
is good.

Correct:

```yaml
models:
  - name: ads_finance_payment_export
    config:
      meta:
        dwd_reason: Finance needs each payment row for the audit export; no DWS keeps that grain.
```

Incorrect:

```yaml
models:
  - name: ads_finance_payment_export
    # the model refs dwd_trade_payment_di but gives no dwd_reason
    config:
      meta: {}
```

Source: Spec §7
Checked by: DWH-L04

### STD-01-05 Accumulating snapshots read transaction facts (MUST)

A DWD whose process has `fact_type: accumulating_snapshot` reads the transaction DWD models of its steps, never ODS.
This keeps one definition of each step event. Such a DWD may therefore read other DWD models.

Correct:

```sql
-- dwd_trade_order_lifecycle_df: process order_lifecycle is an accumulating snapshot
select o.order_id, o.created_at, p.paid_at
from {{ ref('dwd_trade_order_di') }} as o
left join {{ ref('dwd_trade_payment_di') }} as p on p.order_id = o.order_id
```

Incorrect:

```sql
-- dwd_trade_order_lifecycle_df reads ODS directly
select order_id, created_at, paid_at from {{ ref('ods_shop_orders_di') }}
```

Source: Alibaba specify-the-principles-for-using-data-at-different-layers
Checked by: DWH-L04

### STD-01-06 Dependency chains stay short (MUST)

A chain of DIM, DWD and DWS models is at most 10 models deep. A long chain slows the daily run and makes a failure
hard to trace. Split the chain, or move shared work down into one DWD or DIM model. ODS and ADS models are not counted.

Correct:

```text
dws_trade_customer_td -> dws_trade_customer_1d -> dwd_trade_payment_di -> dim_pub_date   # depth 4
```

Incorrect:

```text
step_01 -> step_02 -> ... -> step_11    # 11 models deep inside DIM/DWD/DWS
```

Source: Alibaba specify-the-principles-for-using-data-at-different-layers
Checked by: DWH-L05

### STD-01-07 BI reads the star (SHOULD)

BI tools read DWD plus DIM, and DWS where it exists. Build an ADS model only for a named application, an export or a
measured performance need. An ADS table made "in case someone needs it" is one more table to keep correct.

Correct:

```text
Dashboard "Payments by customer" -> dwd_trade_payment_di + dim_trade_customer
```

Incorrect:

```text
ads_dashboard_payments exists only because the dashboard might be slow; nobody measured it
```

Source: Spec §2

### STD-01-08 One model builds one table (MUST)

Each dbt model or snapshot writes exactly one table. Several tasks never write partitions of the same table: when two
loads share a table, the table has two writers and a rerun of one overwrites the other.

Correct:

```text
model dwd_trade_order_di   -> table dwd_trade_order_di   (one dbt model, one writer)
```

Incorrect:

```text
model order_web  -> inserts partitions into dwd_trade_order_di
model order_app  -> inserts partitions into dwd_trade_order_di   # two writers
```

Source: Alibaba specify-the-principles-for-using-data-at-different-layers
