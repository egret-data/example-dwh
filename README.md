# example-dwh

Kimball/OneData data warehouse on Airflow + dbt-trino + Iceberg.
Design: [docs/en/specs/2026-11-04-kimball-dwh-design.md](docs/en/specs/2026-11-04-kimball-dwh-design.md).
Process guide (terms, flow diagrams, the daily run, backfill): [English](docs/en/guides/data-model-development.md) ·
[Tiếng Việt](docs/vi/guides/data-model-development.md).

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
make e2e               # run dbt_ods_shop in Airflow for 2026-11-02
make dev-down          # stop and delete volumes
```

Ad-hoc dbt inside the image:

```bash
docker compose -f dev/compose.yml run --rm airflow \
  'cd dags/dbt && $DBT_EXECUTABLE_PATH build --select tag:ods_shop --vars "{dt: 2026-11-02}"'
```

## Design metadata and lint

The design lives in `warehouse/*.yml`; the `dwh` tool in `tools/dwh` checks it and the dbt project.

```bash
make validate   # warehouse YAML: JSON Schema and cross-file consistency (DWH-Y)
make dwh-lint   # builds .dbt/target/manifest.json with host-side dbt via uv, then runs `dwh validate` (Y)
                # and the lint families N L M B T D S
make dwh-test   # unit tests of the dwh tool
make catalog    # renders the design catalogue plus dbt docs into site/
make lock       # regenerates requirements.lock and requirements-dbt.lock after a change to requirements*.txt
```

Lint codes are `DWH-<family letter><two digits>`; each finding is one line, `<path>: <code> <message>`,
and any finding makes the command exit 1. Families:

- `Y` warehouse YAML: schema and cross-file consistency
- `N` naming
- `L` layer dependencies and chain depth
- `M` metrics declared and resolvable
- `B` bus matrix: every DWD maps to a cell
- `T` minimum tests per layer
- `D` descriptions present
- `S` source tables declare load type, watermark, timezone and delete handling
- `G` design gate for model-extending changes; runs only in `.github/workflows/design-gate.yml`
  (`dwh design-gate`), not in `make dwh-lint`

## Working with AI tools and the rulebook

`AGENTS.md` is the entry point for every AI coding tool and for people. These files are generated from it and from
`skills/` and are read-only: `CLAUDE.md`, `GEMINI.md`, `.claude/skills/`, `.cursor/rules/` and
`.github/copilot-instructions.md`. Edit `AGENTS.md` or `skills/`, then run `make sync-agents`; CI fails on drift
(`make sync-agents-check`).

The eight skills in `skills/` and when each applies:

| Skill | Use when |
|-------|----------|
| `dwh-start` | any data change request, before anything else |
| `dwh-requirement` | the change is model-extending, or its process, grain, dimensions or metrics are unclear |
| `dwh-model-design` | updating `warehouse/*.yml` and table specifications, before SQL |
| `dwh-implement` | writing or changing dbt models, snapshots, tests or DAGs |
| `dwh-verify` | before saying a change is done, opening a PR or reporting numbers |
| `dwh-review` | reviewing a data PR, your own or someone else's |
| `dwh-debug` | a build, task or query fails, or numbers do not match |
| `dwh-backfill` | past `dt` partitions must be rebuilt |

The rulebook is `docs/standards/` (`00`-`12`). Every rule has an ID `STD-NN-MM`, and `make check-standards` checks the
format and that every lint code it cites exists (DWH-R).

`dwh scaffold` prints (or, with `--write`, creates) the files of a new model from the design in `warehouse/*.yml`,
with empty descriptions so that `dwh lint` fails until you fill them. The design must declare the domain, process,
dimensions and metrics first. The examples below, one per layer, run against the `trade` design in `warehouse/` and
print the files without writing them:

```bash
dwh="uv run --project tools/dwh dwh"
$dwh scaffold ods_shop_orders_di --grain order_id
$dwh scaffold dim_pub_customer --from ods_shop_customers_df   # also writes dim_pub_customer_hist
$dwh scaffold dwd_trade_order_di --from ods_shop_orders_di --grain order_id --event-at created_at
$dwh scaffold dws_trade_customer_1d --from dwd_trade_order_di --grain customer_key \
  --metric order_amt_sum_1d order_cnt_1d
$dwh scaffold ads_crm_customer_value --from dws_trade_customer_td --grain customer_key \
  --metric order_amt_sum_td avg_order_amt_td
```

Style and hooks:

```bash
make sql-lint            # sqlfluff on dags/dbt/models
make pre-commit-install  # install the git hook
make pre-commit          # run every hook on all files
```

To test a change to a skill, run its scenario (`evals/scenarios/`) headless with and without the skills, and let the
LLM judge grade both answers (see `evals/README.md`):

```bash
./evals/run.sh new-source-crm --without-skills   # baseline: no skills or agent instruction files
./evals/run.sh new-source-crm                    # with skills, at HEAD
make eval-all                                    # every scenario, both ways, graded and summarised
```

Answers, grades and summaries go to `evals/results/` (git-ignored).

## The trade reference domain

The `trade` domain (plus the `crm` application layer) is the worked example, built by following the skills.
Design record: [docs/designs/2026-11-04-trade-reference-domain.md](docs/designs/2026-11-04-trade-reference-domain.md).
Models per layer:

| Layer | Models |
|-------|--------|
| ODS | `ods_shop_orders_di` and `ods_shop_payments_di` (incremental by `updated_at`), `ods_shop_customers_df` and `ods_shop_shops_df` (full daily snapshots) |
| DIM | `dim_pub_date` (calendar), `dim_pub_customer` (current row per customer), `dim_pub_customer_hist` (SCD4 snapshot by source `updated_at`), `dim_trade_shop` |
| DWD | `dwd_trade_order_di` (order event by day), `dwd_trade_payment_di` (payment event by pay day), `dwd_trade_order_lifecycle_di` (accumulating snapshot: placed, paid) |
| DWS | `dws_trade_customer_1d`, `dws_trade_customer_nd` (30 days) and `dws_trade_customer_td` (to date) |
| ADS | `ads_crm_customer_value` (average order amount per customer) |

How it was built: the design went into `warehouse/*.yml` first, then each model started from `dwh scaffold --write`
(the commands are in the section above, one per layer, in layer order: ODS, then DIM and DWD, then DWS, then ADS),
and the descriptions, tests and SQL were filled in until `dwh lint` and `dbt test` were clean.

Run it locally:

```bash
make dev-up            # the source fixture is loaded into Postgres
make test-integration  # builds the domain day by day and asserts the expected values
make e2e               # runs the three DAGs below in the image
make eval-all          # runs every skill scenario with and without skills, graded by an LLM judge (costs money)
```

`make e2e` runs these three commands in the Airflow image (`dbt_pub` and `dbt_trade` are asset-scheduled, so
`airflow dags test` gets the day from `--conf`):

```bash
airflow dags test dbt_ods_shop 2026-11-03
airflow dags test dbt_pub 2026-11-03 --conf '{"dt": "2026-11-02"}'
airflow dags test dbt_trade 2026-11-03 --conf '{"dt": "2026-11-02"}'
```

## How it runs in production

- git-sync clones this repo to `/opt/airflow/dags/repo`; Airflow parses only `dags/`.
- dbt runs from `/opt/dbt-venv` inside the image; dbt packages are baked in at build time.
  **Changing `dags/dbt/packages.yml` requires a new image.**
- Every dbt run receives `dt`, the Asia/Ho_Chi_Minh day of the run's data interval
  (`_common.dates.DT_TEMPLATE`), never Airflow's UTC `ds`; each model replaces or merges only its `dt` partition, so re-runs are safe.
