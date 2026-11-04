# 09 — dbt conventions

Scope: materializations, tests, contracts, tags and YAML style for every dbt model, source and snapshot. Names are in
file 02, SQL layout in file 10, incremental mechanics in file 08.

## Rules

### STD-09-01 Materialization per layer (MUST)

ODS, DWD and DWS are incremental with partition replacement (STD-08-04). DIM and ADS are tables, rebuilt in full. The
`_hist` tables of file 04 are snapshots. The default is set per folder in `dbt_project.yml`, so a model does not
repeat it.

Correct:

```yaml
models:
  example_dwh:
    dws:
      +schema: dws
      +materialized: incremental
    ads:
      +schema: ads
      +materialized: table
```

Incorrect:

```yaml
models:
  example_dwh:
    dws:
      +schema: dws
      +materialized: table   # a DWS is incremental; a table rebuilds three years of partitions every day
```

Source: Spec §7

### STD-09-02 Minimum tests (MUST)

Every model has a grain test: `unique` on a single grain column, or `dbt_utils.unique_combination_of_columns`
(DWH-T01). Each grain column has `not_null` (DWH-T02). Each `_key` column of a DWD or DWS has a `relationships` test to
its DIM (DWH-T04). A grain test lists the columns of the grain, so a model with a one-column grain uses `unique`.

Correct:

```yaml
models:
  - name: ods_shop_orders_di
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
  - name: ods_shop_orders_di
    columns:
      - name: order_id
        data_tests: [not_null]
      - name: dt            # grain column without not_null
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns: [order_id, dt]
```

Source: Spec §7
Checked by: DWH-T01, DWH-T02, DWH-T04

### STD-09-03 Contracts on DIM, DWD, DWS (MUST)

DIM, DWD and DWS models set `contract: {enforced: true}` under `config` and give every column a `data_type`. A
contract makes dbt compare the built table with the YAML, so a changed type fails the build instead of reaching
consumers. DWH-T03 checks the contract flag. ODS and ADS need none.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      contract: {enforced: true}
    columns:
      - name: order_key
        data_type: varchar
      - name: dt
        data_type: date
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di   # no contract: a column type can change without a failure
    columns:
      - name: order_key
        data_type: varchar
      - name: dt
        data_type: date
```

Source: Spec §7
Checked by: DWH-T03

### STD-09-04 Tags (MUST)

Layer tags (`layer:ods`, `layer:dwd`, and so on) and the per-source tag (`ods_<source>`) come from `dbt_project.yml`.
A model never sets them by hand. Domain models add `domain:<domain>` in their `.yml`. DAGs select by these tags
(STD-11-02).

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      tags: ["domain:trade"]
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      tags: ["layer:dwd", "domain:trade"]   # the layer tag comes from dbt_project.yml, not from the model
```

Source: Spec §7

### STD-09-05 Describe everything (MUST)

Every model, column and source table has a description (DWH-D01, DWH-D02, DWH-D03). DWH-D02 sees only the columns
listed in the `.yml`, so list every column of the table. A description says what the value means, in business words, and
the model description states the grain.

Correct:

```yaml
models:
  - name: dim_pub_customer
    description: Current customer attributes. Grain: one row per customer.
    columns:
      - name: customer_key
        description: Surrogate key, a hash of customer_id.
      - name: city
        description: City of the customer's default address.
```

Incorrect:

```yaml
models:
  - name: dim_pub_customer
    description: Current customer attributes. Grain: one row per customer.
    columns:
      - name: customer_key
        description: Surrogate key, a hash of customer_id.
      - name: city          # no description
```

Source: Spec §7
Checked by: DWH-D01, DWH-D02, DWH-D03

### STD-09-06 Generic test arguments (MUST)

Under dbt 1.11, a generic test nests its arguments under `arguments:`. Keys written next to the test name are
deprecated. `meta` is written under `config:`, for the same reason: top-level `meta` on a model, column or source is
deprecated.

Correct:

```yaml
columns:
  - name: customer_key
    config:
      meta: {pii: false}
    data_tests:
      - relationships:
          arguments:
            to: ref('dim_pub_customer')
            field: customer_key
```

Incorrect:

```yaml
columns:
  - name: customer_key
    config:
      meta: {pii: false}
    data_tests:
      - relationships:
          to: ref('dim_pub_customer')   # arguments are not nested under arguments:
          field: customer_key
```

Source: Spec §11

### STD-09-07 Start from the scaffold (SHOULD)

Create a model with `dwh scaffold`, so its name, contract, tests and tags start correct and lint-clean. The command
reads the design in `warehouse/` and never overwrites an existing file. Edit the result; do not write the first draft by
hand.

Correct:

```bash
uv run --locked --project tools/dwh dwh scaffold dwd_trade_order_di --from ods_shop_orders_di --write
```

Incorrect:

```text
touch dags/dbt/models/dwd/trade/dwd_trade_order_di.sql   # an empty file: contract, tests and grain are forgotten
```

Source: Spec §6.2
