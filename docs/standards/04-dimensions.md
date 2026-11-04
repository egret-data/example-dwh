# 04 — Dimensions

Scope: dimension tables (`dim_*` and `dim_*_hist`), their keys, their history and their special members. The rules
apply to the DIM layer and to the way DWD tables read it. The source of truth is `warehouse/dimensions.yml`.

Differences from Alibaba:

- SCD types, surrogate and durable keys, special members and inferred members are Kimball techniques. Alibaba's DIM
  page does not cover them.
- Alibaba's guidance kept here: the 10 million row ceiling and daily snapshots.

## Rules

### STD-04-01 SCD4 by default (MUST)

`dim_*` holds one current row per natural key; `dim_*_hist` holds every version. Declare `history: scd4` for every
dimension whose attributes can change, and `scd1` only for a dimension that never changes. The design check (DWH-Y06)
rejects an `scd1` dimension that has a `historical` attribute; it cannot know whether an `scd1` dimension changes in
practice, so that part is a review question.

Correct:

```yaml
dimensions:
  - name: customer
    scope: pub
    description: A buyer.
    natural_key: [customer_id]
    history: scd4
    attributes:
      - {name: city, description: City of the buyer., history: historical}
```

Incorrect:

```yaml
dimensions:
  - name: customer
    scope: pub
    description: A buyer.
    natural_key: [customer_id]
    history: scd1               # the city changes and facts need the old value: use scd4
    attributes:
      - {name: city, description: City of the buyer., history: historical}
```

Source: Kimball (type 4 mini-dimension and history techniques) · Spec §2
Checked by: DWH-Y06

### STD-04-02 Durable keys (MUST)

The key column `<dimension>_key` is `dbt_utils.generate_surrogate_key` over the natural key. It is a hash, so it does
not change between versions and a fact can compute it without looking the dimension up. Facts store this key. The
lint check (DWH-T04) requires every `_key` column of a DWD or DWS to have a `relationships` test to its dimension; it
does not check how the key is computed.

Correct:

```sql
select
    {{ dbt_utils.generate_surrogate_key(['customer_id']) }} as customer_key,
    customer_id,
    city
from {{ ref('ods_shop_customers_df') }}
where dt = (select max(dt) from {{ ref('ods_shop_customers_df') }})
```

Incorrect:

```sql
select
    row_number() over (order by customer_id) as customer_key,   -- a counter changes when rows come or go
    customer_id,
    city
from {{ ref('ods_shop_customers_df') }}
where dt = (select max(dt) from {{ ref('ods_shop_customers_df') }})
```

Source: Kimball (durable keys) · Spec §2
Checked by: DWH-T04

### STD-04-03 History from a snapshot of the current DIM (MUST)

`dim_*_hist` is a dbt snapshot of `dim_*`. Set `unique_key` to the durable key, `strategy: check` with the
historical attributes as `check_cols`, and rename the snapshot columns to `valid_from` and `valid_to`. `is_current` is
derived as `valid_to is null`, never stored. The lint checks cover the name and the dependency: only a snapshot may
be named `dim_*_hist` (DWH-N04), and a snapshot reads a `dim_*` or ODS model (DWH-L04). The key, strategy and column
names are checked in review.

Correct:

```yaml
snapshots:
  - name: dim_pub_customer_hist
    relation: ref('dim_pub_customer')
    description: Every version of a customer; valid_to is null for the current one.
    config:
      unique_key: [customer_key]
      strategy: check
      check_cols: [city]
      snapshot_meta_column_names:
        dbt_valid_from: valid_from
        dbt_valid_to: valid_to
```

Incorrect:

```yaml
snapshots:
  - name: dim_pub_customer_hist
    relation: ref('dim_pub_customer')
    description: Every version of a customer; valid_to is null for the current one.
    config:
      unique_key: [customer_id]   # the natural key, not the durable key
      strategy: check
      check_cols: [city]
      snapshot_meta_column_names:
        dbt_valid_from: valid_from
        dbt_valid_to: valid_to
```

Source: Kimball (type 4) · Spec §11
Checked by: DWH-N04, DWH-L04

### STD-04-04 Historical versus current attributes (MUST)

Each attribute in `dimensions.yml` is `historical` (facts need the value as it was at event time) or `current` (read
from `dim_*` at query time). An `scd1` dimension has only `current` attributes. The check (DWH-Y06) covers the `scd1`
case; for other dimensions the choice is a design decision for the reviewer.

Correct:

```yaml
dimensions:
  - name: shop
    scope: trade
    description: A shop.
    natural_key: [shop_id]
    history: scd1
    attributes:
      - {name: shop_name, description: Shop name., history: current}
```

Incorrect:

```yaml
dimensions:
  - name: shop
    scope: trade
    description: A shop.
    natural_key: [shop_id]
    history: scd1
    attributes:
      - {name: shop_name, description: Shop name., history: historical}   # scd1 keeps no history
```

Source: Kimball (type 1 versus type 2 attributes) · Spec §5
Checked by: DWH-Y06

### STD-04-05 SCD2 only as an exception (MUST)

A per-version surrogate key (SCD2) needs `history: scd2` and a written `scd2_reason`. The JSON schema of
`dimensions.yml` (DWH-Y01) makes the reason mandatory. The default stays SCD4, because facts keep one stable key.

Correct:

```yaml
dimensions:
  - name: contract
    scope: trade
    description: A sales contract.
    natural_key: [contract_id]
    history: scd2
    scd2_reason: Finance reports must join to the exact version signed on the invoice date.
    attributes:
      - {name: status, description: Contract status., history: historical}
```

Incorrect:

```yaml
dimensions:
  - name: contract
    scope: trade
    description: A sales contract.
    natural_key: [contract_id]
    history: scd2               # no scd2_reason
    attributes:
      - {name: status, description: Contract status., history: historical}
```

Source: Kimball (type 2) · Spec §2
Checked by: DWH-Y01

### STD-04-06 Special members (MUST)

Two keys are reserved: `'-1'` means unknown (the natural key is null) and `'-2'` means not applicable. Both are
varchar, like every hash key, and each DIM contains one row for each. The DWD maps a null natural key to `'-1'`
itself, because the hash of a null is a real, wrong key. The special rows carry placeholder natural keys and
descriptive text such as `unknown`. No lint code checks this yet.

Correct:

```sql
-- in dim_pub_customer, after the real rows
union all select '-1', cast(-1 as bigint), 'unknown'
union all select '-2', cast(-2 as bigint), 'not applicable'

-- in the DWD
case
    when customer_id is null then '-1'
    else {{ dbt_utils.generate_surrogate_key(['customer_id']) }}
end as customer_key
```

Incorrect:

```sql
-- in dim_pub_customer, after the real rows
union all select cast(-1 as bigint), cast(-1 as bigint), 'unknown'   -- key is bigint, hash keys are varchar
```

Source: Kimball (special rows) · Spec §7

### STD-04-07 Late-arriving dimensions (MUST)

A fact whose natural key is not yet in the DIM still gets its durable key, because the key is a hash of the natural
key. The DIM inserts an inferred member for it: placeholder attributes and `is_inferred = true`. The next DIM build
finds the real row and replaces the inferred one. Never drop or delay the fact. No lint code checks this yet; the
inferred-member count is a data-quality metric (file 12).

Correct:

```sql
with real_rows as (
    select customer_id, city, false as is_inferred
    from {{ ref('ods_shop_customers_df') }}
    where dt = (select max(dt) from {{ ref('ods_shop_customers_df') }})
),

inferred as (
    select distinct o.customer_id, 'unknown' as city, true as is_inferred
    from {{ ref('ods_shop_orders_di') }} as o
    where o.customer_id is not null
        and o.customer_id not in (select customer_id from real_rows)
)

select {{ dbt_utils.generate_surrogate_key(['customer_id']) }} as customer_key, customer_id, city, is_inferred
from real_rows
union all
select {{ dbt_utils.generate_surrogate_key(['customer_id']) }}, customer_id, city, is_inferred
from inferred
```

Incorrect:

```sql
-- in a DWD: the inner join drops orders of customers the DIM has not loaded yet
select o.order_id, c.customer_key
from {{ ref('ods_shop_orders_di') }} as o
inner join {{ ref('dim_pub_customer') }} as c on c.customer_id = o.customer_id
```

Source: Kimball (late-arriving dimensions) · Spec §7

### STD-04-08 The date dimension (MUST)

`date` is a mandatory pub dimension, built as `dim_pub_date`, with one row per Asia/Ho_Chi_Minh calendar day. The
design check (DWH-Y04) requires the entry in `dimensions.yml` with scope `pub`; it does not check the rows.

Correct:

```yaml
dimensions:
  - name: date
    scope: pub
    description: Calendar day in Asia/Ho_Chi_Minh.
    natural_key: [cal_date]
    history: scd1
    attributes:
      - {name: year, description: Calendar year., history: current}
```

Incorrect:

```yaml
dimensions:
  - name: date
    scope: trade                # the date dimension is shared: scope pub
    description: Calendar day in Asia/Ho_Chi_Minh.
    natural_key: [cal_date]
    history: scd1
    attributes:
      - {name: year, description: Calendar year., history: current}
```

Source: Kimball (calendar date dimension) · Spec §11
Checked by: DWH-Y04

### STD-04-09 Small, stable DIM tables (SHOULD)

A DIM table stays under 10 million rows and is a daily full snapshot (the scaffold builds it as a table that is
rebuilt on each run). A larger one needs a written reason in the model description. Alibaba also advises avoiding
frequent updates and using a map join; Trino chooses the join strategy itself, so only the size and snapshot
guidance carries over.

Correct:

```yaml
models:
  - name: dim_pub_product
    description: >
      Every product. About 40 million rows because the catalogue is merged from three marketplaces;
      splitting it by marketplace would break the one-definition rule.
```

Incorrect:

```yaml
models:
  - name: dim_pub_product
    description: Every product.   # 40 million rows and no reason
```

Source: Alibaba dim-layer

### STD-04-10 Role-playing and degenerate dimensions (MUST)

A role-playing use of a dimension is a bus-matrix role, and the fact column is `<role>_key`. A degenerate dimension
is a transaction identifier kept on the fact, such as `order_id`, with no DIM table. The lint check (DWH-B04)
requires the name of every `_key` column, without `_key`, to be a dimension or a role of the process in
`bus_matrix.yml`.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      meta: {process: order}     # bus_matrix.yml: order uses date as order_date, customer, shop
    columns:
      - name: order_id           # degenerate dimension
      - name: order_date_key
      - name: customer_key
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      meta: {process: order}
    columns:
      - name: order_id
      - name: placed_date_key    # placed_date is not a role of the order process
      - name: customer_key
```

Source: Kimball (role-playing, degenerate dimensions) · Spec §7
Checked by: DWH-B04

### STD-04-11 Mini-dimensions (SHOULD)

Put fast-changing attributes in a separate mini-dimension instead of versioning a large DIM. A band such as a
balance range changes often and takes few values, so a small dimension keeps `dim_*_hist` from growing by a row per
customer per day.

Correct:

```yaml
dimensions:
  - name: customer_band
    scope: trade
    description: Balance band of a customer, one row per band.
    natural_key: [band_id]
    history: scd1
    attributes:
      - {name: band_name, description: Name of the balance band., history: current}
```

Incorrect:

```yaml
dimensions:
  - name: customer
    scope: pub
    description: A buyer.
    natural_key: [customer_id]
    history: scd4
    attributes:
      - {name: balance_band, description: Daily balance band., history: historical}   # a new version per day
```

Source: Kimball (type 4 mini-dimension)
