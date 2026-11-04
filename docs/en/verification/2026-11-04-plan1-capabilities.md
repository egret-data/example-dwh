# Plan 1 — platform capability verification

Measured on: 2026-11-04, at commit b2858b8 (the final-review fix wave). The commit that updates this
record follows it and changes only this file. Every row was produced by one chain run in bash with a
fresh stack (`make dev-down` removed both volumes first):

```bash
make lint && make dev-down && make image && make dev-up && make smoke && make test-dags \
  && make test-integration && make e2e; echo EXIT=$?   # -> EXIT=0
```

| Component | Version |
|-----------|---------|
| Airflow | 3.3.2 (python 3.12) |
| astronomer-cosmos | 1.16.0 |
| dbt-core / dbt-trino | 1.11.16 / 1.11.0 |
| Trino | 483 |
| Iceberg catalog | JDBC (Postgres 17.6), storage RustFS 1.0.1 |

| # | Capability (spec ref) | How measured | Result | Evidence |
|---|-----------------------|--------------|--------|----------|
| C1 | Iceberg partitioned table + Trino MERGE (§4) | `make smoke` + manual output check (the script fails only on SQL errors, not on wrong rows) | PASS | `INSERT: 2 rows`, `MERGE: 2 rows`, final rows `"1","a","2026-11-01"` / `"2","b2","2026-11-02"` / `"3","c","2026-11-02"`, count `"6"` |
| C2 | ODS partition replacement by `dt` is idempotent (§4) | `make test-integration` → `test_ods_shop.py` | PASS | `test_di_loads_only_rows_updated_on_dt`, `test_df_loads_full_copy_into_dt`, `test_rerun_same_dt_is_idempotent`, `test_next_dt_adds_partition_and_keeps_previous` PASSED |
| C3 | dbt-trino `merge` incremental on Iceberg (§10) | `test_capabilities.py::test_merge_*` | PASS | `test_merge_updates_matched_rows_inserts_new_and_moves_partition PASSED` |
| C4 | dbt snapshot (check strategy) on Iceberg (§10, standards 04) | `test_capabilities.py::test_check_snapshot_*` | PASS | `test_check_snapshot_closes_changed_row_and_opens_new_version PASSED`; run total `7 passed in 83.10s` |
| C5 | Cosmos `DBT_LS` render with separate dbt venv | `make test-dags` | PASS | `3 passed, 6 warnings in 15.13s` (warnings are Cosmos importing deprecated `airflow.models.dag.DAG` / `airflow.exceptions`) |
| C6 | Airflow run loads partition for `{{ ds }}` | `make e2e`: `airflow dags test dbt_ods_shop 2026-11-02`, then row counts for that dt (script exits 1 on mismatch) | PASS | `DagRun Finished: dag_id=dbt_ods_shop, logical_date=2026-11-02 ... state=success`; `ods_shop_orders_di dt=2026-11-02 rows: "2"`, `ods_shop_customers_df dt=2026-11-02 rows: "3"`. 2026-11-02 is not `get_dt()`'s default (yesterday = 2026-11-03), so on a fresh stack these rows exist only if `dt` came from `{{ ds }}` |
| C7 | Cosmos emits `trino://` asset events (§4, §10) | `make e2e`: `airflow assets list` + `dev/check_asset_events.py` (exits 1 unless the metadata DB has an `AssetEvent` from `dbt_ods_shop` for each URI) | PASS | Two assets registered (below) and two events: `asset_event uri=trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di source_task_id=ods_shop_orders_di.run`, `asset_event uri=trino://trino:8080/iceberg/dev_ods/ods_shop_customers_df source_task_id=ods_shop_customers_df.run`. Negative check: the script on a fresh metadata DB (no run) printed `no asset event for ...` for both and exited 1 |
| C8 | Re-run with an empty batch clears the `dt` partition (§4) | `test_ods_shop.py::test_rerun_with_empty_batch_clears_the_dt_partition` (deletes the 2026-11-02 source orders, re-runs, restores them in `finally`) | PASS | PASSED at b2858b8. Red first: against the previous `delete+insert` models it failed with `assert 2 == 0` |
| — | Chain runs on a read-only repo mount, like git-sync (F3) | `dev/compose.yml` mounts `..:/opt/airflow/dags/repo:ro`; any write into the repo fails the step | PASS | Whole chain above `EXIT=0` on the `:ro` mount. Probe: `touch dags/dbt/.rw-probe` → `Read-only file system`; `/proc/mounts`: `/opt/airflow/dags/repo ... ro,...` |

C1 notes: Trino 483 does not auto-create the Iceberg JDBC catalog tables, so Task 1 added DDL for `iceberg_tables` and `iceberg_namespace_properties` to `dev/postgres/init/01-init.sql`. Without it the smoke test fails.

## Asset URIs observed

`airflow assets list --output plain` (the flag is supported in 3.3.2; formats: table, json, yaml, plain):

```text
name                                                      uri                                                       group    extra
trino://trino:8080/iceberg/dev_ods/ods_shop_customers_df  trino://trino:8080/iceberg/dev_ods/ods_shop_customers_df  asset    {}
trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di     trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di     asset    {}
```

Observations:

- Only the two `.run` outlets are registered; source inlets (`trino://trino:8080/shop/public/orders`, `.../customers`) appear in task logs but not in the asset list.
- URI form is `trino://<host>:<port>/<catalog>/<schema>/<table>` (path style). Cosmos logs that Airflow 3 rejects the OpenLineage dotted form (`catalog.schema.table`) used under Airflow 2.
- The asset name equals the URI. The schema segment is `dev_ods` in dev and will be `ods` under target `prod`, so downstream `schedule=` assets must be built per environment.
- Task logs warn `AssetModel ... not found; cannot create asset event` / `Emitting event for inactive AssetModel` during `dags test`: the asset rows are created dynamically at first emission (the DAG is not serialized in a test run) and no DAG references them, so they stay inactive (no `asset_active` row). The `AssetEvent` rows are written anyway (C7). Not measured here: that an inactive asset's event triggers a consumer DAG. Plans that add asset-scheduled DAGs must prove that with a serialized consumer.

## Consequences for later plans

All capabilities passed. Deviations discovered during the build that later plans must respect:

- dbt 1.11 requires generic test arguments under `arguments:` in schema YAML.
- Airflow DAG-file safe mode skips files that do not contain the word "airflow"; every DAG file must contain it (import or comment).
- Airflow 3.3.2 `DagBag` has no `include_examples` parameter.
- `dbt deps` in the image must run as root and then be chowned to the airflow user.
- Domain DAGs scheduled on Cosmos assets must use the path-style URIs above, including the environment-specific schema name.
- ODS models replace their `dt` partition with a `pre_hook` delete plus `append`, not `delete+insert` keyed on `dt` (which keeps stale rows when the re-run batch is empty).
- The repo is read-only at runtime: nothing may write into it (bytecode, pytest cache, dbt `target/`, logs or `.user.yml`).
