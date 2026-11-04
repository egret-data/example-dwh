# example-dwh

Kimball/OneData data warehouse on Airflow + dbt-trino + Iceberg.
Design: [docs/en/specs/2026-11-04-kimball-dwh-design.md](docs/en/specs/2026-11-04-kimball-dwh-design.md).

## Layout

| Path | What |
|------|------|
| `dags/` | Airflow dags_folder (git-sync `subPath: dags`) |
| `dags/dbt/` | dbt-trino project; models by layer `ods/ dim/ dwd/ dws/ ads/` |
| `dags/_common/` | shared Cosmos config and default args |
| `dags/sources/` | one DAG per source system (ODS) |
| `dev/` | local stack: Postgres (source + Iceberg JDBC catalog), RustFS, Trino |
| `tests/dags/` | DAG integrity tests (Airflow interpreter) |
| `tests/integration/` | dbt runs against the local stack (dbt venv interpreter) |
| `deploy/helm/` | example values for the official Airflow chart with git-sync |

## Local development

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
make image             # build example-dwh-airflow:dev
make dev-up            # start Postgres, RustFS, Trino (Trino on localhost:28080)
make smoke             # Iceberg + MERGE + source catalog smoke test
make test-dags         # DAG integrity
make test-integration  # ODS idempotency + dbt capability checks
make e2e               # run dbt_ods_shop in Airflow for 2026-11-03
make dev-down          # stop and delete volumes
```

Ad-hoc dbt inside the image:

```bash
docker compose -f dev/compose.yml run --rm airflow \
  'cd dags/dbt && $DBT_EXECUTABLE_PATH build --select tag:ods_shop --vars "{dt: 2026-11-02}"'
```

## How it runs in production

- git-sync clones this repo to `/opt/airflow/dags/repo`; Airflow parses only `dags/`.
- dbt runs from `/opt/dbt-venv` inside the image; dbt packages are baked in at build time.
  **Changing `dags/dbt/packages.yml` requires a new image.**
- Every dbt run receives `dt = {{ ds }}`; each model replaces or merges only its `dt` partition, so re-runs are safe.
