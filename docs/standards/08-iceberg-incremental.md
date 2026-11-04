# 08 — Iceberg tables and incremental loads

Scope: partitions, the business day, source loads and retention for ODS, DWD and DWS tables on Iceberg. DIM and ADS
are full rebuilds (file 09), so only the source, timestamp and retention rules reach them.

## Rules

### STD-08-01 Partition by dt (MUST)

Every ODS, DWD and DWS table is partitioned by `dt`, a DATE. `dt` is the Asia/Ho_Chi_Minh business day, not the
UTC date and not the day the job ran. One partition is the unit of load, re-run, backfill and retention. The
partition property is set in the model's `config`.

Correct:

```sql
{{ config(properties={"partitioning": "ARRAY['dt']"}) }}

select
    cast(order_id as bigint) as order_id,
    date '{{ get_dt() }}'    as dt
from {{ source('shop', 'orders') }}
```

Incorrect:

```sql
{{ config() }}   -- no partitioning property: every run scans and rewrites the whole table

select
    cast(order_id as bigint) as order_id,
    date '{{ get_dt() }}'    as dt
from {{ source('shop', 'orders') }}
```

Source: Spec §2

### STD-08-02 dt comes from the data interval (MUST)

Models read `dt` through `get_dt()`. DAGs hand it to dbt as `--vars` rendered from `_common.dates.DT_TEMPLATE`, which
takes the start of the data interval in Asia/Ho_Chi_Minh. Never use `{{ ds }}`: it is the UTC date of the logical
date, one day off for a schedule that fires at midnight in Vietnam. Without a `dt` variable, `get_dt()` falls back
to yesterday in Vietnam, for manual dev runs only.

Correct:

```python
from _common.dates import DT_TEMPLATE

operator_args = {"vars": {"dt": DT_TEMPLATE}}
```

Incorrect:

```python
operator_args = {"vars": {"dt": "{{ ds }}"}}  # the UTC date, not the business day
```

Source: Spec §4

### STD-08-03 Source timestamps and the day window (MUST)

Select source timestamps with `source_ts(column, tz)`, which reads the naive value in the source's timezone and
returns `timestamp(6) with time zone`. Filter a `di` source with `in_business_day(column, tz)`. It compares the raw
source column with bounds converted to the source timezone, so Trino pushes the predicate down to the source
database. The raw naive column is compared with constants converted to the source zone. In a source zone with
daylight saving time, the skipped or repeated local hour at a transition is assigned to the wrong day, so use the
macros only for zones without it. Asia/Ho_Chi_Minh has none. The zone comes from `source_timezone()`, which reads `config.meta.timezone` of the source.

Correct:

```sql
{% set tz = source_timezone('shop', 'orders') %}

select
    cast(order_id as bigint)          as order_id,
    {{ source_ts('updated_at', tz) }} as updated_at,
    date '{{ get_dt() }}'             as dt
from {{ source('shop', 'orders') }}
where {{ in_business_day('updated_at', tz) }}
```

Incorrect:

```sql
select
    cast(order_id as bigint)  as order_id,
    date '{{ get_dt() }}'     as dt
from {{ source('shop', 'orders') }}
where date(updated_at) = date '{{ get_dt() }}'   -- wraps the source column: no pushdown, no time zone
```

Source: Spec §4

### STD-08-04 Partition replacement (MUST)

A dt-partitioned incremental model replaces its partition: an `is_incremental()`-guarded `pre_hook` deletes the
`dt`, then the model appends its batch. Re-running a day gives the same result, and a day with an empty batch is
cleared too. The two statements are not atomic. If the append fails after the delete, the partition is empty until
the retry restores it, so a failed task is always retried or re-run, never left.

Correct:

```sql
{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}
```

Incorrect:

```sql
{{
  config(
    incremental_strategy='append',   -- no pre_hook: a re-run appends the same day twice
    properties={"partitioning": "ARRAY['dt']"}
  )
}}
```

Source: Spec §4

### STD-08-05 Merge for keyed upserts (SHOULD)

Use `incremental_strategy='merge'` with `unique_key` only for tables updated in place by a key, namely accumulating
snapshots. Document the key in the `.yml` so a reader knows which rows change. Every other incremental table
replaces its partition (STD-08-04), because a merge scans the target for matches and does not clear a re-run's
stale rows.

Correct:

```yaml
models:
  - name: dwd_trade_shipment_acc
    description: Accumulating snapshot, one row per order; merged on order_id as each milestone arrives.
    config:
      incremental_strategy: merge
      unique_key: order_id
```

Incorrect:

```yaml
models:
  - name: dwd_trade_payment_di
    description: One row per payment per day.
    config:
      incremental_strategy: merge   # a transaction fact is never updated in place; replace the partition
      unique_key: payment_id
```

Source: Spec §7

### STD-08-06 Declare every source table (MUST)

Each source table sets `config.meta` with `load` (`di` or `df`), `timezone` (an IANA name, which may be set once on
the source), and `delete_handling` (`none`, `soft_delete_flag` or `full_compare`). A `di` table also sets
`watermark`, the column that decides which rows are in a day. A `di` table with `delete_handling: none` adds
`delete_handling_reason`, because an incremental load cannot see hard deletes. DWH-S01 checks the values and
DWH-S02 checks the reason.

Correct:

```yaml
sources:
  - name: shop
    config:
      meta:
        timezone: Asia/Ho_Chi_Minh
    tables:
      - name: orders
        config:
          meta:
            load: di
            watermark: updated_at
            delete_handling: none
            delete_handling_reason: The shop app cancels orders by status and never deletes order rows.
```

Incorrect:

```yaml
sources:
  - name: shop
    config:
      meta:
        timezone: Asia/Ho_Chi_Minh
    tables:
      - name: orders
        config:
          meta:
            load: di               # no watermark: a di load cannot tell which rows changed
            delete_handling: none
            delete_handling_reason: The shop app cancels orders by status and never deletes order rows.
```

Source: Spec §4
Checked by: DWH-S01, DWH-S02

### STD-08-07 Late-arriving facts (MUST)

A fact can reach the warehouse after its `dt` was loaded. Rebuild the affected dts (skill `dwh-backfill`) instead of
patching rows. A `di` source whose watermark can lag, for example a source that commits rows with an older
`updated_at`, loads with a lookback window, and the window is written in the source's `.yml`. Each run rebuilds one dt, so late
data is handled by re-running the affected dts. The
inferred-member case for dimensions is STD-04-07.

Correct:

```yaml
sources:
  - name: shop
    tables:
      - name: payments
        description: >
          One row per payment. Rows can commit up to 2 days after updated_at. Each run rebuilds one dt; late
          rows are picked up by re-running the affected dts (skill dwh-backfill).
```

Incorrect:

```yaml
sources:
  - name: shop
    tables:
      - name: payments
        description: One row per payment.   # the watermark lags by 2 days, but nothing says how it is handled
```

Source: Kimball (late-arriving facts) · Spec §7

### STD-08-08 Retention (MUST)

Each layer keeps its default retention: ODS 400 days, DWD 3 years, DIM and its `_hist` tables forever, DWS 3 years,
ADS 400 days. A model overrides the default with `config.meta.retention_days`. The rule applies now; the maintenance
DAG that deletes older `dt` partitions, reads `retention_days` and runs the Iceberg cleanup of STD-08-09 arrives with
plan 4.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      meta:
        retention_days: 1825   # 5 years, kept for audit
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di
    retention_days: 1825   # outside config.meta: ignored, the 3-year default applies
```

Source: Alibaba dim-layer · Spec §4

### STD-08-09 Iceberg maintenance (SHOULD)

Compact small files, expire snapshots and remove orphan files on a schedule. Deleting partitions or rows frees no
storage until snapshots expire. Many small files slow every query, so file count and size belong in the performance
baseline (STD-12-05). Use the Trino table procedures. The scheduled job arrives with plan 4, together with the
retention DAG of STD-08-08; until then run them by hand.

Correct:

```sql
alter table ods.ods_shop_orders_di execute optimize;
alter table ods.ods_shop_orders_di execute expire_snapshots(retention_threshold => '7d');
alter table ods.ods_shop_orders_di execute remove_orphan_files(retention_threshold => '7d');
```

Incorrect:

```sql
delete from ods.ods_shop_orders_di where dt < current_date - interval '400' day;
-- the data stays in old snapshots and the files stay in storage: no expire_snapshots follows
```

Source: Alibaba data-warehouse-performance-optimization · Spec §7

### STD-08-10 Timestamps with time zone (MUST)

An `_at` column is `timestamp(6) with time zone`, so an instant means the same thing in every engine and session.
`source_ts()` produces that type. A table built before this rule needs one `--full-refresh`, because
`on_schema_change: fail` stops a type change on an incremental table.

Correct:

```sql
select
    {{ source_ts('created_at', tz) }} as created_at   -- timestamp(6) with time zone
from {{ source('shop', 'orders') }}
```

Incorrect:

```sql
select
    cast(created_at as timestamp(6)) as created_at   -- no time zone: the reader must guess it
from {{ source('shop', 'orders') }}
```

Source: Spec §4
