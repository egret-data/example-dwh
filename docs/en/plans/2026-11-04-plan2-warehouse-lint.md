# Plan 2 — warehouse metadata, `dwh lint` and plan 1 follow-ups

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the warehouse design machine-checkable. `warehouse/*.yml` holds the design, validated by
JSON Schemas. The `dwh` CLI lints the dbt project against it (rule families Y/N/L/M/B/T/D/S, plus the
G design gate) and renders a catalogue. The plan also closes the plan 1 follow-ups: `dt` as the
Asia/Ho_Chi_Minh day, source metadata, locked image dependencies, and SHA-pinned CI actions.

**Architecture:** `tools/dwh` is a small Python package, managed by uv, that reads only YAML and dbt's
`manifest.json`. It never connects to Trino. The manifest is produced on the host by `uvx` dbt
(`make manifest`), so the lint CI job needs no Docker. Each lint rule is a function `Context ->
Iterable[Finding]`, grouped by family in `dwh/rules/<family>.py`. Every rule has a unit test built from
programmatic fixtures in `tools/dwh/tests/fixtures/`.

**Tech Stack:**
- Python 3.12, uv 0.9.x, pyyaml 6.0.3, jsonschema 4.26.0, pytest 9.2.0, hatchling 1.33.0, ruff 0.17.3
- dbt-core 1.11.16 and dbt-trino 1.11.0
- Airflow 3.3.2 and astronomer-cosmos 1.16.0
- Trino 483 with Iceberg

**Spec:** `docs/en/specs/2026-11-04-kimball-dwh-design.md` (§4, §5, §7, §8, §9 item 2, §11).

## Global Constraints

- Branch: `feat/plan2-warehouse-lint` off `main` (at or after `2d601b4`). Never commit to `main`.
- Pinned versions:
  - Airflow `3.3.2` (python3.12); astronomer-cosmos `1.16.0`; Trino `483`.
  - dbt-core `1.11.16`; dbt-trino `1.11.0`; dbt_utils `1.4.1`.
  - pyyaml `6.0.3`; jsonschema `4.26.0`; pytest `9.2.0`; hatchling `1.33.0`; ruff `0.17.3`.
- **D12:** `dt` is the Asia/Ho_Chi_Minh calendar day of the run's data interval. Never use Airflow's
  `{{ ds }}` for `dt`: it is the UTC date of the logical date.
- dbt YAML:
  - Generic test arguments are nested under `arguments:` (dbt ≥ 1.11).
  - `meta` is written under `config:` (`config: {meta: {...}}`).
  - Source-level `config.meta` is inherited by every table of the source.
- Every file under `dags/` that defines a DAG contains the word `airflow`; the DAG processor's safe
  mode skips other files.
- The repository is mounted read-only at runtime: nothing at runtime writes into it. Host-side build
  artefacts go to `.dbt/` and `site/` (both git-ignored).
- `dwh` reads only `warehouse/*.yml`, `warehouse/schemas/*.schema.json` and `manifest.json`. It has no
  Trino connection.
- Lint codes are `DWH-<family letter><two digits>`. Families:
  - `Y` YAML
  - `N` naming
  - `L` layers
  - `M` metrics
  - `B` bus matrix
  - `T` tests
  - `D` descriptions
  - `S` sources
  - `G` design gate

  Output format, one line per finding: `<path>: <code> <message>`. Exit code 1 if there is any
  finding.
- Lint scope:
  - ODS column names mirror the source and are exempt from glossary checks.
  - Every other layer's model and column name tokens must be in `warehouse/glossary.yml`.
- Code, comments, docs, commit messages: English. Commits follow Conventional Commits and end with:

  ```text
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```

- Destructive operations:
  - Integration tests drop only schemas starting with `itest`.
  - Never drop `dev_*` or other schemas.
  - Never `rm -rf` a path built from a variable.
- After each task, `make lint` passes (ruff check and format, line length 110, E501 on).
  `make fmt` wraps code; split any long string literal it cannot wrap by implicit concatenation.

## File map

| Path | Task | Responsibility |
|------|------|----------------|
| `dags/_common/dates.py` | 1 | Business timezone, `DT_TEMPLATE`, daily VN timetable. |
| `dags/_common/dbt.py`, `dags/sources/dbt_ods_shop.py` | 1 | Pass `dt` from `DT_TEMPLATE`; VN timetable. |
| `dags/dbt/macros/source_timezone.sql`, `business_day.sql`, `get_dt.sql` | 1 | Source tz lookup, tz conversion, day window, VN default `dt`. |
| `dags/dbt/models/ods/shop/*` | 1 | Source meta, tz-aware ODS models, unit tests. |
| `tests/dags/test_business_day.py`, `tests/dags/conftest.py` | 1 | `dt` template and timetable tests. |
| `dev/e2e.sh`, `tests/integration/test_ods_shop.py` | 1 | e2e on logical date 2026-11-03 → `dt` 2026-11-02; tz assertions. |
| `Dockerfile`, `requirements.lock`, `requirements-dbt.lock`, `Makefile` | 2 | Locked image installs; `make lock`. |
| `tests/repo/test_locks.py` | 2 | Direct pins appear identically in the locks. |
| `.github/workflows/ci.yml` | 2, 8 | SHA-pinned actions; lint job runs dwh checks. |
| `tools/dwh/**` | 3–8 | The `dwh` package, its tests and fixtures. |
| `warehouse/*.yml`, `warehouse/schemas/*.schema.json` | 3 | Design metadata and its JSON Schemas. |
| `.github/workflows/design-gate.yml` | 7 | Runs `dwh design-gate` on PR events, including label changes. |
| `.github/workflows/catalog.yml` | 8 | Builds and deploys the catalogue to GitHub Pages. |

Out of scope for this plan:
- Plan 3: `dwh scaffold`, `dwh sync-agents`, pre-commit and `dwh lint --changed`.
- Plan 4: the retention maintenance DAG (spec §4), the `dim_pub_date` model and any domain content in
  `warehouse/*.yml`.

Measured before writing this plan (2026-11-04, local stack). The plan depends on these results:

- `CronDataIntervalTimetable("0 0 * * *", timezone="Asia/Ho_Chi_Minh")` infers the interval
  `[2026-11-02 00:00+07, 2026-11-03 00:00+07)` for `run_after` 2026-11-03 (VN or UTC midnight).
- `airflow dags test <dag> 2026-11-03` renders `ds=2026-11-03`, while
  `data_interval_start.in_timezone('Asia/Ho_Chi_Minh').strftime('%Y-%m-%d')` renders `2026-11-02`.
- dbt unit tests:
  - They run on dbt-trino 1.11.0 under `dbt build`. Plain `dbt test` fails unless the model's schema
    already exists.
  - An incremental model needs `overrides.macros.is_incremental`.
  - `graph.sources` does not exist inside unit tests: macros that read it must be overridden.
- With `config.meta` on a source, the manifest's table `meta` contains the merged source + table meta.
  Column `config.meta` appears as column `meta`.
- Host-side runs:
  - `uvx --python 3.12 --from dbt-core --with-requirements requirements-dbt.txt dbt parse` works on
    the host and writes manifest v12.
  - `dbt docs generate --no-compile --empty-catalog --static` works with Trino unreachable.

---

### Task 1: `dt` as the Asia/Ho_Chi_Minh day, and source metadata

**Files:**
- Create: `dags/_common/dates.py`
- Modify: `dags/_common/dbt.py`, `dags/sources/dbt_ods_shop.py`
- Create: `dags/dbt/macros/source_timezone.sql`, `dags/dbt/macros/business_day.sql`
- Modify: `dags/dbt/macros/get_dt.sql`
- Modify: `dags/dbt/models/ods/shop/_shop__sources.yml`, `ods_shop_orders_di.sql`, `ods_shop_customers_df.sql`
- Create: `dags/dbt/models/ods/shop/_shop__unit_tests.yml`
- Modify: `tests/dags/conftest.py`, `tests/dags/test_dag_integrity.py`
- Create: `tests/dags/test_business_day.py`
- Modify: `tests/integration/test_ods_shop.py`, `dev/e2e.sh`

**Interfaces:**
- Produces:
  - `_common.dates.BUSINESS_TZ: str = "Asia/Ho_Chi_Minh"`
  - `_common.dates.DT_TEMPLATE: str`
  - `_common.dates.daily_vn() -> CronDataIntervalTimetable`
  - `_common.dates.vn_date(year, month, day) -> pendulum.DateTime`
  - dbt macros `source_timezone(source_name, table_name)`, `business_tz()`, `source_ts(column, source_tz)`,
    `in_business_day(column, source_tz)`
  - Source `config.meta` keys `timezone`, `load`, `watermark`, `delete_handling`,
    `delete_handling_reason`. Task 4's DWH-S rules read these keys.

- [ ] **Step 1: Move the `dagbag` fixture into `tests/dags/conftest.py`**

Add `import pytest` to the imports at the top of `tests/dags/conftest.py`: importing pytest does not
import Airflow. Then append:

```python
DAGS_DIR = Path(__file__).resolve().parents[2] / "dags"


@pytest.fixture(scope="session")
def dagbag():
    # Imported here, not at module top: Airflow must see the environment variables set above.
    try:
        from airflow.dag_processing.dagbag import DagBag
    except ImportError:  # older import path
        from airflow.models.dagbag import DagBag
    return DagBag(dag_folder=str(DAGS_DIR))
```

In `tests/dags/test_dag_integrity.py`, delete the `try/except` DagBag import, `DAGS_DIR`, the
`dagbag` fixture and the now-unused imports (`Path`, `pytest`). Keep the three tests unchanged.

- [ ] **Step 2: Write the failing DAG-side tests**

Create `tests/dags/test_business_day.py`:

```python
"""D12: dt is the Asia/Ho_Chi_Minh day of the run's data interval, never Airflow's UTC `ds`."""

import pendulum
import pytest
from airflow.timetables.interval import CronDataIntervalTimetable
from jinja2 import Template

from _common.dates import BUSINESS_TZ, DT_TEMPLATE, daily_vn


@pytest.mark.parametrize(
    ("start_utc", "expected"),
    [
        (pendulum.datetime(2026, 11, 1, 17, 0, tz="UTC"), "2026-11-02"),  # 00:00 VN
        (pendulum.datetime(2026, 11, 2, 16, 59, tz="UTC"), "2026-11-02"),  # 23:59 VN
        (pendulum.datetime(2026, 11, 2, 17, 0, tz="UTC"), "2026-11-03"),  # next VN day
    ],
)
def test_dt_template_renders_the_vietnam_day(start_utc, expected):
    assert Template(DT_TEMPLATE).render(data_interval_start=start_utc) == expected


def test_dt_template_does_not_use_ds():
    assert "ds" not in DT_TEMPLATE.replace("data_interval_start", "")


def test_daily_run_covers_the_previous_vietnam_day():
    interval = daily_vn().infer_manual_data_interval(run_after=pendulum.datetime(2026, 11, 3, tz=BUSINESS_TZ))

    assert interval.start == pendulum.datetime(2026, 11, 2, tz=BUSINESS_TZ)
    assert interval.end == pendulum.datetime(2026, 11, 3, tz=BUSINESS_TZ)


def test_ods_shop_dag_uses_the_vn_timetable_and_dt_template(dagbag):
    dag = dagbag.get_dag("dbt_ods_shop")

    assert isinstance(dag.timetable, CronDataIntervalTimetable)
    interval = dag.timetable.infer_manual_data_interval(run_after=pendulum.datetime(2026, 11, 3, tz="UTC"))
    assert interval.start == pendulum.datetime(2026, 11, 2, tz=BUSINESS_TZ)
    for task in dag.tasks:
        assert task.vars == {"dt": DT_TEMPLATE}, task.task_id
```

- [ ] **Step 3: Run them and see them fail**

Run: `make test-dags` (the repo is mounted into the container; no image rebuild needed)
Expected: FAIL. `test_business_day.py` errors on `ModuleNotFoundError: No module named '_common.dates'`.

- [ ] **Step 4: Implement `_common/dates.py` and wire the DAG**

Create `dags/_common/dates.py`:

```python
"""The business day `dt` (spec D12): the Asia/Ho_Chi_Minh calendar day of a run's data interval."""

import pendulum
from airflow.timetables.interval import CronDataIntervalTimetable

BUSINESS_TZ = "Asia/Ho_Chi_Minh"

# Rendered by Airflow at run time. Never `{{ ds }}`: that is the UTC date of the logical date and is
# one day off for a midnight-VN schedule.
DT_TEMPLATE = "{{ data_interval_start.in_timezone('" + BUSINESS_TZ + "').strftime('%Y-%m-%d') }}"


def daily_vn() -> CronDataIntervalTimetable:
    """Runs at 00:00 Asia/Ho_Chi_Minh; each run covers the previous VN day [00:00, 24:00)."""
    return CronDataIntervalTimetable("0 0 * * *", timezone=BUSINESS_TZ)


def vn_date(year: int, month: int, day: int) -> pendulum.DateTime:
    return pendulum.datetime(year, month, day, tz=BUSINESS_TZ)
```

In `dags/_common/dbt.py`:
- add `from _common.dates import DT_TEMPLATE` after the cosmos imports;
- replace the last entry of the returned dict with:

```python
        # Passed to run time only (templated), so `dbt ls` at parse time never renders it.
        "operator_args": {"vars": {"dt": DT_TEMPLATE}},
```

Replace `dags/sources/dbt_ods_shop.py` with:

```python
"""Airflow DAG: load source system `shop` into ODS (Iceberg) for the Vietnam business day."""

from cosmos import DbtDag

from _common.dates import daily_vn, vn_date
from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS

dbt_ods_shop = DbtDag(
    dag_id="dbt_ods_shop",
    schedule=daily_vn(),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:ods", "source:shop"],
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
```

- [ ] **Step 5: Run the DAG tests**

Run: `make test-dags`
Expected: PASS, 9 passed: 3 integrity tests and 6 business-day items (the parametrised test counts
as 3).

- [ ] **Step 6: Write the failing dbt unit tests**

Create `dags/dbt/models/ods/shop/_shop__unit_tests.yml`:

```yaml
version: 2

# D12 boundary tests: dt is the Asia/Ho_Chi_Minh day. dbt unit tests have no graph.sources, so
# source_timezone is always overridden here; the real lookup is covered by the integration tests.
unit_tests:
  - name: orders_di_window_is_the_vietnam_day
    model: ods_shop_orders_di
    overrides:
      vars: {dt: "2026-11-02"}
      macros: {is_incremental: false, source_timezone: Asia/Ho_Chi_Minh}
    given:
      - input: source('shop', 'orders')
        rows:
          - {order_id: 1, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-01 23:00:00", updated_at: "2026-11-01 23:30:00"}
          - {order_id: 2, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-01 23:00:00", updated_at: "2026-11-02 00:30:00"}
          - {order_id: 3, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-02 23:00:00", updated_at: "2026-11-02 23:30:00"}
          - {order_id: 4, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-02 23:00:00", updated_at: "2026-11-03 00:30:00"}
    expect:
      rows:
        - {order_id: 2}
        - {order_id: 3}

  - name: orders_di_converts_a_utc_source_to_the_vietnam_day
    model: ods_shop_orders_di
    overrides:
      vars: {dt: "2026-11-02"}
      macros: {is_incremental: false, source_timezone: UTC}
    given:
      - input: source('shop', 'orders')
        rows:
          # 16:30 UTC = 23:30 VN on the previous day; 17:30 UTC = 00:30 VN on the next day.
          - {order_id: 1, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-01 16:00:00", updated_at: "2026-11-01 16:30:00"}
          - {order_id: 2, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-01 16:00:00", updated_at: "2026-11-01 17:30:00"}
          - {order_id: 3, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-02 16:00:00", updated_at: "2026-11-02 16:30:00"}
          - {order_id: 4, customer_id: 1, order_status: paid, total_amount: 1, created_at: "2026-11-02 16:00:00", updated_at: "2026-11-02 17:30:00"}
    expect:
      rows:
        - {order_id: 2}
        - {order_id: 3}
```

Run (stack up: `make dev-up`):

```bash
docker compose -f dev/compose.yml run --rm -e DBT_SCHEMA=itest_ut airflow \
  'cd dags/dbt && $DBT_EXECUTABLE_PATH build --select ods_shop_orders_di --vars "{dt: 2026-11-02}"'
```

Expected: FAIL. `orders_di_converts_a_utc_source_to_the_vietnam_day` fails because the current model
filters naive timestamps with no conversion, or the build errors because the macro `source_timezone`
does not exist yet. Either outcome is red; record which one in the report.

Clean up the schema afterwards with the drop helper:

```bash
docker compose -f dev/compose.yml run --rm airflow \
  "cd tests/integration && /opt/dbt-venv/bin/python -c 'from helpers import drop_schemas; drop_schemas(\"itest_ut\")'"
```

- [ ] **Step 7: Implement the macros and the tz-aware ODS models**

Create `dags/dbt/macros/source_timezone.sql`:

```sql
{#
  IANA timezone of a source table's naive timestamps, from the source's `config.meta.timezone`
  (dbt merges source-level meta into each table's meta). dbt unit tests have no graph.sources, so
  every unit test overrides this macro.
#}
{% macro source_timezone(source_name, table_name) -%}
  {%- if not execute -%}
    {{- return('UTC') -}}
  {%- endif -%}
  {%- for node in graph.sources.values() -%}
    {%- if node.source_name == source_name and node.name == table_name -%}
      {%- set tz = node.meta.get('timezone') -%}
      {%- if not tz -%}
        {{- exceptions.raise_compiler_error('source ' ~ source_name ~ '.' ~ table_name ~ ' has no meta.timezone') -}}
      {%- endif -%}
      {{- return(tz) -}}
    {%- endif -%}
  {%- endfor -%}
  {{- exceptions.raise_compiler_error('unknown source ' ~ source_name ~ '.' ~ table_name) -}}
{%- endmacro %}
```

Create `dags/dbt/macros/business_day.sql`:

```sql
{#
  Spec D12: `dt` is the Asia/Ho_Chi_Minh calendar day.
  source_ts() turns a naive source timestamp into timestamp(6) with time zone, read in the source's
  timezone. in_business_day() keeps rows whose instant falls in [dt 00:00, dt+1 00:00)
  Asia/Ho_Chi_Minh. Asia/Ho_Chi_Minh has no DST, so "+ interval '1' day" is exactly 24 hours.
#}
{% macro business_tz() -%}
  {{- return('Asia/Ho_Chi_Minh') -}}
{%- endmacro %}

{% macro source_ts(column, source_tz) -%}
with_timezone(cast({{ column }} as timestamp(6)), '{{ source_tz }}')
{%- endmacro %}

{% macro in_business_day(column, source_tz) -%}
{%- set day_start = "with_timezone(timestamp '" ~ get_dt() ~ " 00:00:00', '" ~ business_tz() ~ "')" -%}
{{ source_ts(column, source_tz) }} >= {{ day_start }}
    and {{ source_ts(column, source_tz) }} < {{ day_start }} + interval '1' day
{%- endmacro %}
```

Replace `dags/dbt/macros/get_dt.sql` with:

```sql
{#
  The partition date being processed, as 'YYYY-MM-DD': the Asia/Ho_Chi_Minh business day (spec D12).
  Airflow passes --vars '{dt: ...}' rendered from _common.dates.DT_TEMPLATE.
  Default, for manual dev runs: yesterday in Asia/Ho_Chi_Minh.
  Validated only at execution time, because `dbt ls`/parse render with placeholder values.
#}
{% macro get_dt() -%}
  {%- set today_vn = modules.datetime.datetime.now(modules.pytz.timezone('Asia/Ho_Chi_Minh')).date() -%}
  {%- set default_dt = (today_vn - modules.datetime.timedelta(days=1)).isoformat() -%}
  {%- set dt = var('dt', default_dt) | string -%}
  {%- if execute -%}
    {%- do modules.datetime.date.fromisoformat(dt) -%}
  {%- endif -%}
  {{- return(dt) -}}
{%- endmacro %}
```

Replace `dags/dbt/models/ods/shop/_shop__sources.yml` with:

```yaml
version: 2

sources:
  - name: shop
    description: Shop OLTP database (Trino catalog `shop`, Postgres connector).
    database: shop
    schema: public
    config:
      meta:
        # The shop database stores naive TIMESTAMP columns in Vietnam local time.
        timezone: Asia/Ho_Chi_Minh
    tables:
      - name: orders
        description: One row per order; updated in place.
        config:
          meta:
            load: di
            watermark: updated_at
            delete_handling: none
            delete_handling_reason: The shop app cancels orders by status and never deletes order rows.
      - name: customers
        description: One row per customer; updated in place.
        config:
          meta:
            load: df
            delete_handling: none
```

Replace `dags/dbt/models/ods/shop/ods_shop_orders_di.sql` with:

```sql
{#
  Daily increment of shop.orders for the Vietnam business day dt (spec D12).
  Replace the dt partition: delete it first, then append the batch. Unlike delete+insert keyed
  on dt, this also clears the partition when the re-run batch is empty.
#}
{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set tz = source_timezone('shop', 'orders') %}

select
    cast(order_id as bigint)             as order_id,
    cast(customer_id as bigint)          as customer_id,
    cast(order_status as varchar)        as order_status,
    cast(total_amount as decimal(18, 2)) as total_amount,
    {{ source_ts('created_at', tz) }}    as created_at,
    {{ source_ts('updated_at', tz) }}    as updated_at,
    date '{{ get_dt() }}'                as dt
from {{ source('shop', 'orders') }}
where {{ in_business_day('updated_at', tz) }}
```

Replace `dags/dbt/models/ods/shop/ods_shop_customers_df.sql` with:

```sql
{#
  Daily full copy of shop.customers into the Vietnam business day dt (spec D12).
  Replace the dt partition: delete it first, then append the batch. Unlike delete+insert keyed
  on dt, this also clears the partition when the re-run batch is empty.
#}
{{
  config(
    incremental_strategy='append',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where dt = date '{{ get_dt() }}'{% endif %}",
    properties={"partitioning": "ARRAY['dt']"}
  )
}}

{% set tz = source_timezone('shop', 'customers') %}

select
    cast(customer_id as bigint)       as customer_id,
    cast(customer_name as varchar)    as customer_name,
    cast(city as varchar)             as city,
    {{ source_ts('created_at', tz) }} as created_at,
    {{ source_ts('updated_at', tz) }} as updated_at,
    date '{{ get_dt() }}'             as dt
from {{ source('shop', 'customers') }}
```

- [ ] **Step 8: Run the unit tests green**

Re-run the Step 6 build command.
Expected: PASS. Both unit tests pass, the model builds, and the data tests pass. Then drop
`itest_ut` with the Step 6 cleanup command.

- [ ] **Step 9: Extend the integration tests and the e2e**

In `tests/integration/test_ods_shop.py`, make `build` return dbt's stdout:

```python
def build(dt: str) -> str:
    return run_dbt(MAIN_PROJECT, ["build", "--select", "tag:ods_shop", "--vars", f"{{dt: '{dt}'}}"], SCHEMA)
```

and add these two tests directly after `test_rerun_same_dt_is_idempotent`:

```python
def test_vietnam_day_unit_tests_run_in_the_ods_build():
    out = build("2026-11-02")

    assert "orders_di_window_is_the_vietnam_day" in out
    assert "orders_di_converts_a_utc_source_to_the_vietnam_day" in out


def test_timestamps_are_stored_with_time_zone():
    rows = query(
        f"SELECT column_name, data_type FROM {CATALOG}.information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}_ods' AND table_name = 'ods_shop_orders_di' "
        "AND column_name IN ('created_at', 'updated_at') ORDER BY column_name"
    )

    assert rows == [
        ("created_at", "timestamp(6) with time zone"),
        ("updated_at", "timestamp(6) with time zone"),
    ]
```

The existing counts do not change: the `shop` fixture is in Vietnam local time, so the VN day of every
fixture row equals its naive date.

In `dev/e2e.sh`, replace the header comment, the `DT=` line and the `airflow dags test` line:

```bash
# Runs dbt_ods_shop for logical date 2026-11-03 inside the Airflow image, then checks data, registered
# assets and AssetEvent rows. Its data interval is the Vietnam day 2026-11-02, so dt = 2026-11-02 while
# Airflow's UTC {{ ds }} is 2026-11-03. The orders fixture has 2 rows on 2026-11-02 and 3 on
# 2026-11-03, so the row check proves dt comes from the VN data interval (spec D12), not from ds.
```

```bash
LOGICAL_DATE=2026-11-03
DT=2026-11-02
```

```bash
  airflow dags test $DAG $LOGICAL_DATE
```

- [ ] **Step 10: Run the full local chain**

Run, on a fresh stack:

```bash
bash -c 'set -o pipefail; make dev-down && make image && make dev-up && make smoke && make test-dags \
  && make test-integration && make e2e; echo EXIT=$?' 2>&1 | tee /tmp/plan2-task1-chain.log | tail -30
```

Expected:
- the chain ends with `EXIT=0`;
- test-integration shows 9 passed;
- e2e prints `ods_shop_orders_di dt=2026-11-02 rows: "2"` and `e2e OK`.

- [ ] **Step 11: Commit**

```bash
git add dags tests dev/e2e.sh
git commit -m "feat(dbt): make dt the Asia/Ho_Chi_Minh business day and declare source metadata" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Locked image dependencies and SHA-pinned CI actions

**Files:**
- Modify: `Dockerfile`, `Makefile`, `.github/workflows/ci.yml`
- Create (generated): `requirements.lock`, `requirements-dbt.lock`
- Create: `tests/repo/test_locks.py`

**Interfaces:**
- Produces:
  - `make lock` regenerates both lock files.
  - `make test-repo` runs `tests/repo`.
  - The image installs only from the lock files.

- [ ] **Step 1: Write the failing lock test**

Create `tests/repo/test_locks.py`:

```python
"""Every direct pin in requirements*.txt is pinned identically in its lock file."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path: Path) -> dict[str, str]:
    found = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        assert sep, f"{path.name}: not pinned with ==: {raw!r}"
        found[canonical(name.split("[", 1)[0])] = version.strip()
    return found


@pytest.mark.parametrize(
    ("requirements", "lock"),
    [("requirements.txt", "requirements.lock"), ("requirements-dbt.txt", "requirements-dbt.lock")],
)
def test_direct_pins_are_locked_at_the_same_version(requirements, lock):
    direct = pins(REPO / requirements)
    locked = pins(REPO / lock)

    for name, version in direct.items():
        assert locked.get(name) == version, f"{name}: {requirements} pins {version}, {lock} has {locked.get(name)}"
```

Add to the `Makefile` (and to `.PHONY`):

```make
test-repo:
	uvx --from pytest==9.2.0 pytest -p no:cacheprovider tests/repo -v
```

Run: `make test-repo`
Expected: FAIL with `FileNotFoundError` on `requirements.lock`.

- [ ] **Step 2: Restructure the Dockerfile**

Replace `Dockerfile` with:

```dockerfile
# syntax=docker/dockerfile:1
FROM apache/airflow:3.3.2-python3.12 AS runtime

USER root
RUN python -m venv /opt/dbt-venv \
    && mkdir -p /opt/dbt_packages /tmp/dbt \
    && chown -R airflow: /opt/dbt-venv /opt/dbt_packages /tmp/dbt
USER airflow

# `make lock` only: resolve the direct requirements (Airflow side under Airflow's official
# constraints) and freeze the result into requirements*.lock. Never used by the real image.
FROM runtime AS resolve
COPY --chown=airflow requirements.txt requirements-dbt.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
      -c https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt \
    && /opt/dbt-venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

FROM runtime AS base
# Exact, complete pins: --no-deps means nothing outside the lock files can be installed.
COPY --chown=airflow requirements.lock requirements-dbt.lock /tmp/
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.lock \
    && /opt/dbt-venv/bin/pip install --no-cache-dir --no-deps -r /tmp/requirements-dbt.lock \
    && pip check \
    && /opt/dbt-venv/bin/pip check

# DBT_SEND_ANONYMOUS_USAGE_STATS=false: no .user.yml cookie written into the read-only profiles dir.
ENV DBT_EXECUTABLE_PATH=/opt/dbt-venv/bin/dbt \
    DBT_PACKAGES_INSTALL_PATH=/opt/dbt_packages \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

# Bake dbt packages; git-sync delivers models but never runs `dbt deps`.
# Runs as root: `dbt deps` rmtree()s the install dir itself, which needs write access to /opt.
COPY dags/dbt/dbt_project.yml dags/dbt/packages.yml dags/dbt/package-lock.yml /tmp/dbt-deps/
USER root
RUN cd /tmp/dbt-deps && /opt/dbt-venv/bin/dbt deps \
    && rm -rf /tmp/dbt-deps \
    && chown -R airflow: /opt/dbt_packages /tmp/dbt
USER airflow

FROM base AS dev
RUN pip install --no-cache-dir pytest==9.2.0 \
    && /opt/dbt-venv/bin/pip install --no-cache-dir pytest==9.2.0

FROM base AS prod
```

If `pip check` fails, run `docker run --rm --entrypoint pip apache/airflow:3.3.2-python3.12 check` to
see whether the failure is already in the upstream image:
- If it is, remove only the system `pip check` line, keep the dbt venv check, and record the upstream
  output in the report.
- If it is not, stop and report: the resolve stage produced an inconsistent set.

- [ ] **Step 3: Add `make lock` and generate the locks**

Add to the `Makefile` (and to `.PHONY`):

```make
lock:
	docker build --target resolve -t example-dwh-airflow:resolve .
	{ echo '# Generated by `make lock` from requirements.txt (Airflow 3.3.2 constraints). Do not edit.'; \
	  docker run --rm --entrypoint pip example-dwh-airflow:resolve freeze; } > requirements.lock
	{ echo '# Generated by `make lock` from requirements-dbt.txt. Do not edit.'; \
	  docker run --rm --entrypoint /opt/dbt-venv/bin/pip example-dwh-airflow:resolve freeze; } > requirements-dbt.lock
```

Run: `make lock && grep -cE '==' requirements.lock requirements-dbt.lock && ! grep -n ' @ ' requirements.lock requirements-dbt.lock`
Expected:
- more than 400 pins in `requirements.lock` and more than 50 in `requirements-dbt.lock`;
- no ` @ ` (URL) lines: the final `! grep` prints nothing and succeeds.

If `grep` prints lines, stop and report them.

- [ ] **Step 4: Lock test green, image builds from the locks**

Run: `make test-repo && make image`
Expected: test PASS (2 passed); the image builds, including `pip check`.

- [ ] **Step 5: Pin CI actions to commit SHAs and run the repo test in CI**

In `.github/workflows/ci.yml`:
- replace every `actions/checkout@v4` with `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`;
- replace `astral-sh/setup-uv@v6` with `astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3`;
- add `- run: make test-repo` after `- run: make lint` in the `lint` job.

These SHAs are the release commits resolved on 2026-11-04 with
`gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`.

- [ ] **Step 6: Run the full local chain**

Run the Task 1 Step 10 chain command, adding `make lint && make test-repo &&` at the front.
Expected: `EXIT=0`.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile Makefile requirements.lock requirements-dbt.lock tests/repo .github/workflows/ci.yml
git commit -m "build: install the image from generated lock files and pin CI actions to SHAs" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The `dwh` package, `warehouse/` YAML, JSON Schemas and `dwh validate` (DWH-Y)

**Files:**
- Create: `tools/dwh/pyproject.toml`, `tools/dwh/.python-version`, `tools/dwh/uv.lock` (generated)
- Create: `tools/dwh/src/dwh/__init__.py`, `findings.py`, `warehouse.py`, `yaml_rules.py`, `validate.py`, `cli.py`
- Create: `tools/dwh/tests/conftest.py`, `tools/dwh/tests/fixtures/__init__.py`, `tools/dwh/tests/fixtures/warehouse.py`
- Create: `tools/dwh/tests/test_validate.py`
- Create: `warehouse/{domains,processes,dimensions,bus_matrix,metrics,modifiers,periods,glossary}.yml`
- Create: `warehouse/schemas/{domains,processes,dimensions,bus_matrix,metrics,modifiers,periods,glossary}.schema.json`
- Modify: `pyproject.toml` (ruff), `Makefile`, `.gitignore`

**Interfaces:**
- Produces:
  - `dwh.findings.Finding(path: str, code: str, message: str)`: frozen, ordered by (path, code, message); `.render() -> str`
  - `dwh.findings.rel(path) -> str`
  - `dwh.warehouse.FILES: tuple[str, ...]`; `dwh.warehouse.load_warehouse(root: Path) -> Warehouse`
  - `Warehouse` members:
    - methods `.path(name)`, `.items(file, key)`, `.by_name(file, key)`
    - properties `.domains`, `.processes`, `.dimensions`, `.modifier_types`, `.modifiers`, `.atomic`,
      `.derived`, `.calculated`, `.periods` (each `dict[name, dict]`)
    - `.words: set[str]`; `.bus: dict[process, row]`
  - `dwh.validate.validate(root: Path, schema_dir: Path | None = None) -> list[Finding]`
  - `dwh.cli.main(argv: list[str] | None = None) -> int` with subcommand `validate`
  - Test fixtures:
    - `fixtures.warehouse.MINIMAL: dict` and `write_warehouse(dir, mutate=None, drop=()) -> Path`
    - pytest fixture `make_warehouse(mutate=None, drop=()) -> Path`

- [ ] **Step 1: Package scaffolding**

Create `tools/dwh/pyproject.toml`:

```toml
[project]
name = "dwh"
version = "0.1.0"
description = "example-dwh design metadata, lint and catalogue CLI"
requires-python = ">=3.12"
dependencies = ["pyyaml==6.0.3", "jsonschema==4.26.0"]

[project.scripts]
dwh = "dwh.cli:main"

[dependency-groups]
dev = ["pytest==9.2.0"]

[build-system]
requires = ["hatchling==1.33.0"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/dwh"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `tools/dwh/.python-version` containing `3.12`, and an empty `tools/dwh/src/dwh/__init__.py`
holding only the docstring `"""example-dwh design metadata tools (spec §5, §8)."""`.

In the root `pyproject.toml`, set:

```toml
src = ["dags", "tests", "tools/dwh/src", "tools/dwh/tests"]
```

and

```toml
known-first-party = ["_common", "dwh", "fixtures"]
```

Append `.dbt/` and `site/` to `.gitignore`.

Add to the `Makefile` (and to `.PHONY`):

```make
DWH := uv run --locked --project tools/dwh dwh

dwh-test:
	uv run --locked --project tools/dwh pytest -p no:cacheprovider tools/dwh/tests -v

validate:
	$(DWH) validate --warehouse warehouse
```

- [ ] **Step 2: Write the JSON Schemas**

Create `warehouse/schemas/domains.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/domains.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["domains"],
  "properties": {
    "domains": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "description", "owner"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*$", "description": "One token: it fills one segment of table names."},
          "description": {"type": "string", "minLength": 1},
          "owner": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

Create `warehouse/schemas/processes.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/processes.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["processes"],
  "properties": {
    "processes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "domain", "description", "fact_type", "grain"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
          "domain": {"type": "string", "pattern": "^[a-z][a-z0-9]*$"},
          "description": {"type": "string", "minLength": 1},
          "fact_type": {"enum": ["transaction", "periodic_snapshot", "accumulating_snapshot"]},
          "grain": {"type": "string", "minLength": 1, "description": "One sentence: what one fact row is."}
        }
      }
    }
  }
}
```

Create `warehouse/schemas/dimensions.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/dimensions.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["dimensions"],
  "properties": {
    "dimensions": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "scope", "description", "natural_key", "history", "attributes"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
          "scope": {"type": "string", "pattern": "^[a-z][a-z0-9]*$", "description": "pub, or the one domain that owns the dimension."},
          "description": {"type": "string", "minLength": 1},
          "natural_key": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"}},
          "history": {"enum": ["scd1", "scd4", "scd2"], "description": "scd4 is the default (spec D11); scd2 needs scd2_reason."},
          "scd2_reason": {"type": "string", "minLength": 1},
          "attributes": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["name", "description", "history"],
              "properties": {
                "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
                "description": {"type": "string", "minLength": 1},
                "history": {"enum": ["historical", "current"]}
              }
            }
          }
        },
        "if": {"properties": {"history": {"const": "scd2"}}, "required": ["history"]},
        "then": {"required": ["scd2_reason"]}
      }
    }
  }
}
```

Create `warehouse/schemas/bus_matrix.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/bus_matrix.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["bus_matrix"],
  "properties": {
    "bus_matrix": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["process", "dimensions"],
        "properties": {
          "process": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
          "dimensions": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["dimension"],
              "properties": {
                "dimension": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
                "role": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$", "description": "Role name for a role-playing dimension, e.g. order_date."}
              }
            }
          }
        }
      }
    }
  }
}
```

Create `warehouse/schemas/metrics.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/metrics.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["atomic", "derived", "calculated"],
  "$defs": {
    "snake": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"}
  },
  "properties": {
    "atomic": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "process", "description", "aggregation", "additivity"],
        "properties": {
          "name": {"$ref": "#/$defs/snake"},
          "process": {"$ref": "#/$defs/snake"},
          "description": {"type": "string", "minLength": 1},
          "aggregation": {"enum": ["sum", "count", "count_distinct", "min", "max"]},
          "additivity": {"enum": ["additive", "semi_additive", "non_additive"]},
          "non_additive_dimension": {"$ref": "#/$defs/snake"}
        },
        "if": {"properties": {"additivity": {"const": "semi_additive"}}, "required": ["additivity"]},
        "then": {"required": ["non_additive_dimension"]}
      }
    },
    "derived": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "atomic", "period", "grain", "description"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z0-9]+(_[a-z0-9]+)*$"},
          "atomic": {"$ref": "#/$defs/snake"},
          "period": {"enum": ["1d", "nd", "td", "1w", "hh", "mm"]},
          "days": {"type": "integer", "minimum": 2, "description": "Length of an nd period."},
          "modifiers": {"type": "array", "items": {"$ref": "#/$defs/snake"}},
          "grain": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/snake"}},
          "description": {"type": "string", "minLength": 1}
        },
        "if": {"properties": {"period": {"const": "nd"}}, "required": ["period"]},
        "then": {"required": ["days"]},
        "else": {"not": {"required": ["days"]}}
      }
    },
    "calculated": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "formula", "inputs", "description"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z0-9]+(_[a-z0-9]+)*$"},
          "formula": {"type": "string", "minLength": 1},
          "inputs": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": "^[a-z0-9]+(_[a-z0-9]+)*$"}},
          "description": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

Create `warehouse/schemas/modifiers.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/modifiers.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["modifier_types", "modifiers"],
  "properties": {
    "modifier_types": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "domain", "description"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
          "domain": {"type": "string", "pattern": "^[a-z][a-z0-9]*$"},
          "description": {"type": "string", "minLength": 1}
        }
      }
    },
    "modifiers": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "type", "predicate", "processes", "description"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
          "type": {"type": "string", "pattern": "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"},
          "predicate": {"type": "string", "minLength": 1, "description": "The business filter in words or SQL."},
          "processes": {"type": "array", "minItems": 1, "items": {"type": "string"}},
          "description": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

Create `warehouse/schemas/periods.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/periods.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["periods"],
  "properties": {
    "periods": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "description"],
        "properties": {
          "name": {"enum": ["1d", "nd", "td", "1w", "hh", "mm"]},
          "description": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

Create `warehouse/schemas/glossary.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "warehouse/glossary.yml",
  "type": "object",
  "additionalProperties": false,
  "required": ["words"],
  "properties": {
    "words": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["word", "meaning"],
        "properties": {
          "word": {"type": "string", "pattern": "^[a-z0-9]+$"},
          "meaning": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

- [ ] **Step 3: Write the repository's warehouse files**

Create `warehouse/domains.yml`:

```yaml
# Data domains (spec §5). Each name is one token: it fills one segment of table names.
# Adding a domain is model-extending: it needs a docs/designs/ record and the design-approved label.
domains: []
```

Create `warehouse/processes.yml`:

```yaml
# Business processes (spec §5). fact_type: transaction | periodic_snapshot | accumulating_snapshot.
# grain is one sentence saying what one fact row is. Adding a process is model-extending.
processes: []
```

Create `warehouse/dimensions.yml`:

```yaml
# Conformed dimensions (spec §5, D11). history: scd4 (default) | scd1 | scd2 (needs scd2_reason).
# Attribute history: historical (resolved in DWD at event time) | current (read from dim_*).
dimensions:
  - name: date
    scope: pub
    description: Calendar day in the Asia/Ho_Chi_Minh calendar. Mandatory as dim_pub_date.
    natural_key: [cal_date]
    history: scd1
    attributes:
      - name: year
        description: Calendar year.
        history: current
      - name: month
        description: Calendar month, 1-12.
        history: current
      - name: weekday
        description: ISO day of week, 1 = Monday.
        history: current
```

Create `warehouse/bus_matrix.yml`:

```yaml
# Process x dimension matrix (spec §5). role names a role-playing use, e.g. order_date.
bus_matrix: []
```

Create `warehouse/metrics.yml`:

```yaml
# Metrics (spec §5, 06-metrics). Derived metric name = {modifiers}_{atomic}_{agg}_{period},
# where agg is sum | cnt | dcnt | min | max and an nd period renders as <days>d.
# Non-additive results are calculated metrics over stored numerator/denominator metrics.
atomic: []
derived: []
calculated: []
```

Create `warehouse/modifiers.yml`:

```yaml
# Business filters (Alibaba "modifiers", spec §5). A modifier inherits its domain from its type.
modifier_types: []
modifiers: []
```

Create `warehouse/periods.yml`:

```yaml
# Statistical periods (spec §5). One period per DWS table; batch DWS defaults to 1d / nd / td.
periods:
  - name: 1d
    description: The dt day.
  - name: nd
    description: The last n days up to and including dt; n is fixed by each derived metric (days).
  - name: td
    description: All history up to and including dt.
  - name: 1w
    description: The last 7 days, split out of an nd table that grew too wide.
  - name: hh
    description: Hourly.
  - name: mm
    description: Minute-level.
```

Create `warehouse/glossary.yml`:

```yaml
# Root words allowed in model and column names outside ODS (spec §7, 02-naming).
words:
  - {word: ods, meaning: Operational data store layer.}
  - {word: dim, meaning: Dimension layer.}
  - {word: dwd, meaning: Detail fact layer.}
  - {word: dws, meaning: Summary layer.}
  - {word: ads, meaning: Application layer.}
  - {word: pub, meaning: Shared across domains.}
  - {word: hist, meaning: All versions of a dimension (SCD4 history table).}
  - {word: di, meaning: Daily incremental load.}
  - {word: df, meaning: Daily full load.}
  - {word: dt, meaning: Partition date, the Asia/Ho_Chi_Minh business day.}
  - {word: id, meaning: Natural identifier from a source.}
  - {word: key, meaning: Surrogate or durable key.}
  - {word: is, meaning: Boolean flag prefix.}
  - {word: at, meaning: Timestamp suffix.}
  - {word: amt, meaning: Money amount.}
  - {word: cnt, meaning: Count.}
  - {word: dcnt, meaning: Distinct count.}
  - {word: sum, meaning: Sum aggregation.}
  - {word: min, meaning: Minimum aggregation.}
  - {word: max, meaning: Maximum aggregation.}
  - {word: avg, meaning: Average, a calculated metric.}
  - {word: date, meaning: Calendar day.}
  - {word: cal, meaning: Calendar.}
  - {word: year, meaning: Calendar year.}
  - {word: month, meaning: Calendar month.}
  - {word: weekday, meaning: Day of week.}
  - {word: name, meaning: Display name.}
  - {word: inferred, meaning: Placeholder member for a late-arriving dimension row.}
  - {word: valid, meaning: Validity range of a history row (valid_from, valid_to).}
  - {word: from, meaning: Start of a range.}
  - {word: to, meaning: End of a range.}
  - {word: current, meaning: The current version of a dimension row (is_current).}
```

- [ ] **Step 4: Write the test fixtures**

Create `tools/dwh/tests/fixtures/__init__.py` with the docstring
`"""Programmatic lint fixtures (spec §8.1: every rule has a failing fixture)."""`.

Create `tools/dwh/tests/fixtures/warehouse.py`:

```python
"""A small, coherent warehouse design. Tests copy it and break one thing at a time."""

import copy
from collections.abc import Callable, Iterable
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
SCHEMAS = REPO / "warehouse" / "schemas"

WORDS = (
    "ods dim dwd dws ads pub hist di df dt id key is at amt cnt dcnt sum min max avg "
    "date cal year month weekday name inferred trade order shipment ship customer city shop "
    "app channel buyer bi daily status"
).split()

MINIMAL: dict = {
    "domains": {"domains": [{"name": "trade", "description": "Orders and shipments.", "owner": "data-eng"}]},
    "processes": {
        "processes": [
            {
                "name": "order",
                "domain": "trade",
                "description": "A buyer places an order.",
                "fact_type": "transaction",
                "grain": "One row per order.",
            },
            {
                "name": "shipment",
                "domain": "trade",
                "description": "An order moves from placed to delivered.",
                "fact_type": "accumulating_snapshot",
                "grain": "One row per order, updated at each milestone.",
            },
        ]
    },
    "dimensions": {
        "dimensions": [
            {
                "name": "date",
                "scope": "pub",
                "description": "Calendar day.",
                "natural_key": ["cal_date"],
                "history": "scd1",
                "attributes": [{"name": "year", "description": "Year.", "history": "current"}],
            },
            {
                "name": "customer",
                "scope": "pub",
                "description": "A buyer.",
                "natural_key": ["customer_id"],
                "history": "scd4",
                "attributes": [{"name": "city", "description": "City.", "history": "historical"}],
            },
            {
                "name": "shop",
                "scope": "trade",
                "description": "A shop.",
                "natural_key": ["shop_id"],
                "history": "scd1",
                "attributes": [{"name": "shop_name", "description": "Shop name.", "history": "current"}],
            },
        ]
    },
    "bus_matrix": {
        "bus_matrix": [
            {
                "process": "order",
                "dimensions": [
                    {"dimension": "date", "role": "order_date"},
                    {"dimension": "customer"},
                    {"dimension": "shop"},
                ],
            },
            {"process": "shipment", "dimensions": [{"dimension": "date", "role": "ship_date"}, {"dimension": "customer"}]},
        ]
    },
    "metrics": {
        "atomic": [
            {
                "name": "order_amt",
                "process": "order",
                "description": "Order amount.",
                "aggregation": "sum",
                "additivity": "additive",
            },
            {"name": "order", "process": "order", "description": "Orders.", "aggregation": "count", "additivity": "additive"},
            {
                "name": "order_buyer",
                "process": "order",
                "description": "Distinct buyers.",
                "aggregation": "count_distinct",
                "additivity": "non_additive",
            },
        ],
        "derived": [
            {
                "name": "order_amt_sum_1d",
                "atomic": "order_amt",
                "period": "1d",
                "grain": ["customer"],
                "description": "Order amount per customer per day.",
            },
            {
                "name": "app_order_amt_sum_30d",
                "atomic": "order_amt",
                "period": "nd",
                "days": 30,
                "modifiers": ["app"],
                "grain": ["customer"],
                "description": "App order amount per customer, last 30 days.",
            },
            {
                "name": "order_cnt_1d",
                "atomic": "order",
                "period": "1d",
                "grain": ["customer"],
                "description": "Orders per customer per day.",
            },
        ],
        "calculated": [
            {
                "name": "avg_order_amt_1d",
                "formula": "order_amt_sum_1d / order_cnt_1d",
                "inputs": ["order_amt_sum_1d", "order_cnt_1d"],
                "description": "Average order amount per customer per day.",
            }
        ],
    },
    "modifiers": {
        "modifier_types": [{"name": "channel", "domain": "trade", "description": "Sales channel."}],
        "modifiers": [
            {
                "name": "app",
                "type": "channel",
                "predicate": "channel = 'app'",
                "processes": ["order"],
                "description": "Orders placed in the mobile app.",
            }
        ],
    },
    "periods": {
        "periods": [{"name": p, "description": f"Period {p}."} for p in ("1d", "nd", "td", "1w", "hh", "mm")]
    },
    "glossary": {"words": [{"word": w, "meaning": f"Meaning of {w}."} for w in WORDS]},
}


def write_warehouse(
    directory: Path, mutate: Callable[[dict], None] | None = None, drop: Iterable[str] = ()
) -> Path:
    """Write MINIMAL (after `mutate`) as YAML files into `directory`, linking the real schemas."""
    files = copy.deepcopy(MINIMAL)
    if mutate:
        mutate(files)
    directory.mkdir(parents=True)
    (directory / "schemas").symlink_to(SCHEMAS, target_is_directory=True)
    for name, data in files.items():
        if name not in drop:
            (directory / f"{name}.yml").write_text(yaml.safe_dump(data, sort_keys=False))
    return directory
```

Create `tools/dwh/tests/conftest.py`:

```python
import itertools

import pytest
from fixtures.warehouse import write_warehouse


@pytest.fixture
def make_warehouse(tmp_path):
    counter = itertools.count()

    def _make(mutate=None, drop=()):
        return write_warehouse(tmp_path / f"warehouse{next(counter)}", mutate=mutate, drop=drop)

    return _make
```

- [ ] **Step 5: Write the failing validate tests**

Create `tools/dwh/tests/test_validate.py`:

```python
from fixtures.warehouse import REPO

from dwh.cli import main
from dwh.validate import validate


def codes(findings):
    return [f.code for f in findings]


def test_minimal_fixture_warehouse_is_clean(make_warehouse):
    assert validate(make_warehouse()) == []


def test_repository_warehouse_is_clean():
    assert validate(REPO / "warehouse") == []


def test_y01_missing_file(make_warehouse):
    findings = validate(make_warehouse(drop=["periods"]))

    assert codes(findings) == ["DWH-Y01"]
    assert findings[0].path.endswith("periods.yml")


def test_y01_schema_violation_names_the_field(make_warehouse):
    def mutate(files):
        files["processes"]["processes"][0]["fact_type"] = "weird"

    findings = validate(make_warehouse(mutate=mutate))

    assert codes(findings) == ["DWH-Y01"]
    assert "$.processes[0].fact_type" in findings[0].message


def test_y01_nd_period_requires_days(make_warehouse):
    def mutate(files):
        del files["metrics"]["derived"][1]["days"]

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y01"]


def test_y02_duplicate_process(make_warehouse):
    def mutate(files):
        processes = files["processes"]["processes"]
        processes.append(dict(processes[0]))

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y02"]


def test_y03_process_with_unknown_domain(make_warehouse):
    def mutate(files):
        files["processes"]["processes"][0]["domain"] = "crm"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03"]


def test_y03_bus_matrix_with_unknown_dimension(make_warehouse):
    def mutate(files):
        files["bus_matrix"]["bus_matrix"][0]["dimensions"][2]["dimension"] = "store"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03"]


def test_y03_derived_metric_with_unknown_atomic(make_warehouse):
    def mutate(files):
        files["metrics"]["derived"][0]["atomic"] = "gmv"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03"]


def test_y04_date_dimension_is_mandatory(make_warehouse):
    def mutate(files):
        dims = files["dimensions"]["dimensions"]
        files["dimensions"]["dimensions"] = [d for d in dims if d["name"] != "date"]

    # The two bus-matrix cells that use `date` also become unknown references.
    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y03", "DWH-Y03", "DWH-Y04"]


def test_y05_name_token_not_in_glossary(make_warehouse):
    def mutate(files):
        attributes = files["dimensions"]["dimensions"][1]["attributes"]
        attributes.append({"name": "segment", "description": "Segment.", "history": "current"})

    findings = validate(make_warehouse(mutate=mutate))

    assert codes(findings) == ["DWH-Y05"]
    assert "'segment'" in findings[0].message


def test_y06_scd1_dimension_with_historical_attribute(make_warehouse):
    def mutate(files):
        files["dimensions"]["dimensions"][0]["attributes"][0]["history"] = "historical"

    assert codes(validate(make_warehouse(mutate=mutate))) == ["DWH-Y06"]


def test_cli_validate_reports_and_exits_1(make_warehouse, capsys):
    def mutate(files):
        files["dimensions"]["dimensions"][0]["attributes"][0]["history"] = "historical"

    rc = main(["validate", "--warehouse", str(make_warehouse(mutate=mutate))])

    out = capsys.readouterr().out
    assert rc == 1
    assert ": DWH-Y06 " in out
    assert out.strip().endswith("1 finding(s)")


def test_cli_validate_clean_exits_0(make_warehouse, capsys):
    assert main(["validate", "--warehouse", str(make_warehouse())]) == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"
```

Run: `uv lock --project tools/dwh && make dwh-test`
Expected: FAIL. Collection errors with `ModuleNotFoundError: No module named 'dwh.cli'`.

- [ ] **Step 6: Implement findings, warehouse, YAML rules, validate and the CLI**

Create `tools/dwh/src/dwh/findings.py`:

```python
"""A lint finding and how it is printed."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.code} {self.message}"


def rel(path: Path | str) -> str:
    """`path` relative to the working directory when it is inside it, else absolute."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)
```

Create `tools/dwh/src/dwh/warehouse.py`:

```python
"""Load warehouse/*.yml (spec §5) into one read-only object."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dwh.findings import rel

FILES = ("domains", "processes", "dimensions", "bus_matrix", "metrics", "modifiers", "periods", "glossary")


@dataclass(frozen=True)
class Warehouse:
    root: Path
    data: dict[str, Any]

    def path(self, name: str) -> str:
        return rel(self.root / f"{name}.yml")

    def items(self, file: str, key: str) -> list[dict]:
        return list((self.data.get(file) or {}).get(key) or [])

    def by_name(self, file: str, key: str) -> dict[str, dict]:
        return {item["name"]: item for item in self.items(file, key)}

    @property
    def domains(self) -> dict[str, dict]:
        return self.by_name("domains", "domains")

    @property
    def processes(self) -> dict[str, dict]:
        return self.by_name("processes", "processes")

    @property
    def dimensions(self) -> dict[str, dict]:
        return self.by_name("dimensions", "dimensions")

    @property
    def modifier_types(self) -> dict[str, dict]:
        return self.by_name("modifiers", "modifier_types")

    @property
    def modifiers(self) -> dict[str, dict]:
        return self.by_name("modifiers", "modifiers")

    @property
    def atomic(self) -> dict[str, dict]:
        return self.by_name("metrics", "atomic")

    @property
    def derived(self) -> dict[str, dict]:
        return self.by_name("metrics", "derived")

    @property
    def calculated(self) -> dict[str, dict]:
        return self.by_name("metrics", "calculated")

    @property
    def periods(self) -> dict[str, dict]:
        return self.by_name("periods", "periods")

    @property
    def words(self) -> set[str]:
        return {item["word"] for item in self.items("glossary", "words")}

    @property
    def bus(self) -> dict[str, dict]:
        return {row["process"]: row for row in self.items("bus_matrix", "bus_matrix")}


def load_warehouse(root: Path) -> Warehouse:
    data = {}
    for name in FILES:
        path = root / f"{name}.yml"
        data[name] = yaml.safe_load(path.read_text()) if path.exists() else {}
    return Warehouse(root, data)
```

Create `tools/dwh/src/dwh/yaml_rules.py`:

```python
"""DWH-Y02..Y06: consistency of warehouse/*.yml beyond what the JSON Schemas express (DWH-Y01)."""

import re
from collections import Counter
from collections.abc import Iterator

from dwh.findings import Finding
from dwh.warehouse import Warehouse

# Period tokens inside metric names (1d, 30d, 12h, nd, td, hh, mm) are not glossary words.
PERIOD_TOKEN = re.compile(r"^(\d+[dhmw]|nd|td|hh|mm)$")

UNIQUE_COLLECTIONS = (
    ("domains", "domains", "name"),
    ("processes", "processes", "name"),
    ("dimensions", "dimensions", "name"),
    ("modifiers", "modifier_types", "name"),
    ("modifiers", "modifiers", "name"),
    ("periods", "periods", "name"),
    ("glossary", "words", "word"),
    ("bus_matrix", "bus_matrix", "process"),
)


def y02_unique_names(wh: Warehouse) -> Iterator[Finding]:
    for file, key, field in UNIQUE_COLLECTIONS:
        counts = Counter(item[field] for item in wh.items(file, key))
        for name, n in sorted(counts.items()):
            if n > 1:
                yield Finding(wh.path(file), "DWH-Y02", f"{key}: {name!r} is defined {n} times")
    metric_names = Counter(
        metric["name"] for section in ("atomic", "derived", "calculated") for metric in wh.items("metrics", section)
    )
    for name, n in sorted(metric_names.items()):
        if n > 1:
            yield Finding(wh.path("metrics"), "DWH-Y02", f"metric {name!r} is defined {n} times")


def y03_references(wh: Warehouse) -> Iterator[Finding]:
    domains, processes, dimensions = set(wh.domains), set(wh.processes), set(wh.dimensions)
    metrics = set(wh.atomic) | set(wh.derived) | set(wh.calculated)

    def missing(file: str, where: str, value: str, known: set[str], kind: str) -> Iterator[Finding]:
        if value not in known:
            yield Finding(wh.path(file), "DWH-Y03", f"{where}: unknown {kind} {value!r}")

    for p in wh.items("processes", "processes"):
        yield from missing("processes", f"process {p['name']}", p["domain"], domains, "domain")
    for d in wh.items("dimensions", "dimensions"):
        if d["scope"] != "pub":
            yield from missing("dimensions", f"dimension {d['name']}", d["scope"], domains, "domain (scope)")
    for row in wh.items("bus_matrix", "bus_matrix"):
        yield from missing("bus_matrix", "bus_matrix row", row["process"], processes, "process")
        for cell in row["dimensions"]:
            where = f"bus_matrix row {row['process']}"
            yield from missing("bus_matrix", where, cell["dimension"], dimensions, "dimension")
    for t in wh.items("modifiers", "modifier_types"):
        yield from missing("modifiers", f"modifier type {t['name']}", t["domain"], domains, "domain")
    for m in wh.items("modifiers", "modifiers"):
        yield from missing("modifiers", f"modifier {m['name']}", m["type"], set(wh.modifier_types), "modifier type")
        for p in m["processes"]:
            yield from missing("modifiers", f"modifier {m['name']}", p, processes, "process")
    for a in wh.items("metrics", "atomic"):
        where = f"atomic metric {a['name']}"
        yield from missing("metrics", where, a["process"], processes, "process")
        if "non_additive_dimension" in a:
            yield from missing("metrics", where, a["non_additive_dimension"], dimensions, "dimension")
    for d in wh.items("metrics", "derived"):
        where = f"derived metric {d['name']}"
        yield from missing("metrics", where, d["atomic"], set(wh.atomic), "atomic metric")
        yield from missing("metrics", where, d["period"], set(wh.periods), "period")
        for m in d.get("modifiers", []):
            yield from missing("metrics", where, m, set(wh.modifiers), "modifier")
        for g in d["grain"]:
            yield from missing("metrics", where, g, dimensions, "dimension")
    for c in wh.items("metrics", "calculated"):
        for i in c["inputs"]:
            yield from missing("metrics", f"calculated metric {c['name']}", i, metrics, "metric")


def y04_date_dimension(wh: Warehouse) -> Iterator[Finding]:
    date = wh.dimensions.get("date")
    if date is None or date["scope"] != "pub":
        yield Finding(wh.path("dimensions"), "DWH-Y04", "dimension 'date' with scope 'pub' is mandatory (dim_pub_date)")


def name_tokens(name: str) -> list[str]:
    return [token for token in name.split("_") if not PERIOD_TOKEN.match(token)]


def y05_glossary(wh: Warehouse) -> Iterator[Finding]:
    words = wh.words

    def check(file: str, kind: str, name: str) -> Iterator[Finding]:
        for token in name_tokens(name):
            if token not in words:
                yield Finding(wh.path(file), "DWH-Y05", f"{kind} {name}: {token!r} is not in glossary.yml")

    for d in wh.items("domains", "domains"):
        yield from check("domains", "domain", d["name"])
    for p in wh.items("processes", "processes"):
        yield from check("processes", "process", p["name"])
    for d in wh.items("dimensions", "dimensions"):
        yield from check("dimensions", "dimension", d["name"])
        for key in d["natural_key"]:
            yield from check("dimensions", f"dimension {d['name']} natural key", key)
        for attribute in d["attributes"]:
            yield from check("dimensions", f"dimension {d['name']} attribute", attribute["name"])
    for row in wh.items("bus_matrix", "bus_matrix"):
        for cell in row["dimensions"]:
            if "role" in cell:
                yield from check("bus_matrix", f"bus_matrix row {row['process']} role", cell["role"])
    for t in wh.items("modifiers", "modifier_types"):
        yield from check("modifiers", "modifier type", t["name"])
    for m in wh.items("modifiers", "modifiers"):
        yield from check("modifiers", "modifier", m["name"])
    for section in ("atomic", "derived", "calculated"):
        for metric in wh.items("metrics", section):
            yield from check("metrics", f"{section} metric", metric["name"])


def y06_scd1_attributes_are_current(wh: Warehouse) -> Iterator[Finding]:
    for d in wh.items("dimensions", "dimensions"):
        if d["history"] != "scd1":
            continue
        for attribute in d["attributes"]:
            if attribute["history"] == "historical":
                yield Finding(
                    wh.path("dimensions"),
                    "DWH-Y06",
                    f"dimension {d['name']}: attribute {attribute['name']} is historical but the dimension is scd1",
                )


YAML_RULES = [y02_unique_names, y03_references, y04_date_dimension, y05_glossary, y06_scd1_attributes_are_current]
```

Create `tools/dwh/src/dwh/validate.py`:

```python
"""`dwh validate`: JSON Schema (DWH-Y01) first, then the cross-file YAML rules (DWH-Y02..)."""

import json
from collections.abc import Iterator
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from dwh.findings import Finding, rel
from dwh.warehouse import FILES, load_warehouse
from dwh.yaml_rules import YAML_RULES


def schema_findings(root: Path, schema_dir: Path) -> Iterator[Finding]:
    for name in FILES:
        path = root / f"{name}.yml"
        if not path.exists():
            yield Finding(rel(path), "DWH-Y01", "file is missing")
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            yield Finding(rel(path), "DWH-Y01", f"invalid YAML: {exc}")
            continue
        schema = json.loads((schema_dir / f"{name}.schema.json").read_text())
        for error in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: e.json_path):
            yield Finding(rel(path), "DWH-Y01", f"{error.json_path}: {error.message}")


def validate(root: Path, schema_dir: Path | None = None) -> list[Finding]:
    """All DWH-Y findings for the warehouse at `root`. Cross-file rules run only on schema-valid YAML."""
    findings = list(schema_findings(root, schema_dir or root / "schemas"))
    if findings:
        return sorted(set(findings))
    warehouse = load_warehouse(root)
    return sorted({finding for rule in YAML_RULES for finding in rule(warehouse)})
```

Create `tools/dwh/src/dwh/cli.py`:

```python
"""The `dwh` command line."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dwh.findings import Finding
from dwh.validate import validate


def report(findings: Sequence[Finding]) -> int:
    for finding in findings:
        print(finding.render())
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


def cmd_validate(args: argparse.Namespace) -> int:
    return report(validate(args.warehouse))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dwh", description="example-dwh design metadata tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate warehouse/*.yml (DWH-Y rules)")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run the tests and the real validation**

Run: `make dwh-test && make validate && make lint`
Expected:
- dwh-test: 14 passed;
- validate prints `0 finding(s)` and exits 0;
- lint: clean (run `make fmt` first if the formatter wants changes, then re-run).

- [ ] **Step 8: Commit**

```bash
git add tools/dwh warehouse pyproject.toml Makefile .gitignore
git commit -m "feat(dwh): add warehouse design YAML, JSON Schemas and dwh validate" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Manifest loader, `dwh lint` engine and families D, S, T

**Files:**
- Create: `tools/dwh/src/dwh/manifest.py`, `lint.py`, `rules/__init__.py`, `rules/docs.py`, `rules/sources.py`, `rules/testing.py`
- Modify: `tools/dwh/src/dwh/cli.py`
- Create: `tools/dwh/tests/fixtures/manifest.py`
- Modify: `tools/dwh/tests/conftest.py`
- Create: `tools/dwh/tests/test_manifest.py`, `test_rules_docs.py`, `test_rules_sources.py`, `test_rules_testing.py`, `test_lint.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: Task 3 `Finding`, `Warehouse`, `load_warehouse`, `validate`, `report`, `build_parser`.
- Produces:
  - `dwh.manifest`:
    - `LAYERS = ("ods", "dim", "dwd", "dws", "ads")`
    - dataclasses `Column`, `Node`, `SourceTable`, `DataTest`, `Project`
    - `load_manifest(path: Path) -> Project`
  - `Node` members:
    - fields `.unique_id`, `.name`, `.resource_type` (`"model"` | `"snapshot"`), `.path`, `.description`,
      `.meta`, `.columns: dict[str, Column]`, `.depends_on: tuple[str, ...]`, `.contract_enforced`
    - properties `.layer: str | None` and `.folder: str | None`
  - `Project` methods: `.models()`, `.refs(node)`, `.source_deps(node)`, `.tests_for(unique_id)`
  - `dwh.lint.Context(warehouse, project)`, `dwh.lint.Rule`, `dwh.lint.run_lint(ctx, rules=None) -> list[Finding]`
  - `dwh.rules.FAMILIES` (a tuple of modules, each with `RULES`) and `dwh.rules.ALL_RULES`
  - Fixtures:
    - `fixtures.manifest.ManifestBuilder`
    - `fixtures.manifest.good_project() -> tuple[ManifestBuilder, dict[str, str]]`: a project that is
      clean for **every** family in this plan
    - pytest fixture `lint(builder, mutate=None, prefix=None) -> list[str]` (finding codes)
  - CLI: `dwh lint --warehouse DIR --manifest FILE [--select PREFIX ...]`
  - Makefile: `make manifest` (writes `.dbt/target/manifest.json`), `make dwh-lint`

- [ ] **Step 1: Write the manifest fixture builder**

Create `tools/dwh/tests/fixtures/manifest.py`:

```python
"""Build dbt manifest dicts (schema v12 subset that dwh reads) without running dbt."""

import copy

PROJECT = "example_dwh"


def _columns(columns: dict | None) -> dict:
    out = {}
    for name, spec in (columns or {}).items():
        spec = {"description": spec} if isinstance(spec, str) else spec
        out[name] = {"name": name, "description": spec.get("description", ""), "meta": spec.get("meta", {})}
    return out


class ManifestBuilder:
    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._sources: dict[str, dict] = {}
        self._tests = 0

    def source(self, source_name, table, *, description="A source table.", meta=None) -> str:
        uid = f"source.{PROJECT}.{source_name}.{table}"
        self._sources[uid] = {
            "unique_id": uid,
            "resource_type": "source",
            "package_name": PROJECT,
            "source_name": source_name,
            "name": table,
            "description": description,
            "meta": dict(meta or {}),
            "original_file_path": f"models/ods/{source_name}/_{source_name}__sources.yml",
        }
        return uid

    def model(self, name, path, *, deps=(), columns=None, meta=None, contract=False, description="A model.",
              resource_type="model") -> str:
        uid = f"{resource_type}.{PROJECT}.{name}"
        self._nodes[uid] = {
            "unique_id": uid,
            "resource_type": resource_type,
            "package_name": PROJECT,
            "name": name,
            "original_file_path": path,
            "description": description,
            "meta": dict(meta or {}),
            "columns": _columns(columns),
            "depends_on": {"nodes": list(deps)},
            "contract": {"enforced": contract},
        }
        return uid

    def snapshot(self, name, path, **kwargs) -> str:
        return self.model(name, path, resource_type="snapshot", **kwargs)

    def test(self, test_name, model, *, column=None, namespace=None, **kwargs) -> str:
        self._tests += 1
        uid = f"test.{PROJECT}.{test_name}_{self._tests}"
        test_kwargs = dict(kwargs)
        if column:
            test_kwargs["column_name"] = column
        self._nodes[uid] = {
            "unique_id": uid,
            "resource_type": "test",
            "package_name": PROJECT,
            "name": f"{test_name}_{self._tests}",
            "attached_node": model,
            "column_name": column,
            "test_metadata": {"name": test_name, "namespace": namespace, "kwargs": test_kwargs},
            "depends_on": {"nodes": [model]},
        }
        return uid

    def unique(self, model, column) -> str:
        return self.test("unique", model, column=column)

    def not_null(self, model, column) -> str:
        return self.test("not_null", model, column=column)

    def unique_combo(self, model, columns) -> str:
        return self.test("unique_combination_of_columns", model, namespace="dbt_utils",
                         combination_of_columns=list(columns))

    def relationships(self, model, column, to, field) -> str:
        return self.test("relationships", model, column=column, to=f"ref('{to.split('.')[-1]}')", field=field)

    def node(self, uid) -> dict:
        """The live node dict, for tests that break one property."""
        return self._nodes[uid]

    def source_node(self, uid) -> dict:
        return self._sources[uid]

    def find_tests(self, model, test_name, column=None) -> list[str]:
        return [
            uid
            for uid, n in self._nodes.items()
            if n["resource_type"] == "test"
            and n["attached_node"] == model
            and n["test_metadata"]["name"] == test_name
            and (column is None or n["column_name"] == column)
        ]

    def remove(self, uid) -> None:
        self._nodes.pop(uid)

    def build(self) -> dict:
        return {
            "metadata": {
                "project_name": PROJECT,
                "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
            },
            "nodes": copy.deepcopy(self._nodes),
            "sources": copy.deepcopy(self._sources),
        }


def good_project() -> tuple[ManifestBuilder, dict[str, str]]:
    """ODS -> SCD4 DIM -> DWD -> DWS -> ADS for fixtures.warehouse.MINIMAL; clean for every lint family."""
    b = ManifestBuilder()
    ids: dict[str, str] = {}
    ids["orders"] = b.source("shop", "orders", meta={
        "timezone": "Asia/Ho_Chi_Minh", "load": "di", "watermark": "updated_at", "delete_handling": "soft_delete_flag",
    })
    ids["customers"] = b.source("shop", "customers", meta={
        "timezone": "Asia/Ho_Chi_Minh", "load": "df", "delete_handling": "none",
    })

    ids["ods_orders"] = b.model("ods_shop_orders_di", "models/ods/shop/ods_shop_orders_di.sql", deps=[ids["orders"]],
                                columns={"order_id": "Order id.", "dt": "Partition date."})
    b.unique_combo(ids["ods_orders"], ["order_id", "dt"])
    b.not_null(ids["ods_orders"], "order_id")
    b.not_null(ids["ods_orders"], "dt")

    ids["ods_customers"] = b.model("ods_shop_customers_df", "models/ods/shop/ods_shop_customers_df.sql",
                                   deps=[ids["customers"]], columns={"customer_id": "Customer id.", "dt": "Partition date."})
    b.unique_combo(ids["ods_customers"], ["customer_id", "dt"])
    b.not_null(ids["ods_customers"], "customer_id")
    b.not_null(ids["ods_customers"], "dt")

    ids["hist"] = b.snapshot("dim_pub_customer_hist", "snapshots/dim_pub_customer_hist.yml",
                             deps=[ids["ods_customers"]],
                             columns={"customer_key": "Durable key.", "customer_id": "Customer id.", "city": "City."})

    ids["dim_customer"] = b.model("dim_pub_customer", "models/dim/pub/dim_pub_customer.sql", deps=[ids["ods_customers"]],
                                  contract=True,
                                  columns={"customer_key": "Durable key.", "customer_id": "Customer id.", "city": "City."})
    b.unique(ids["dim_customer"], "customer_key")
    b.not_null(ids["dim_customer"], "customer_key")

    ids["dwd_order"] = b.model("dwd_trade_order_di", "models/dwd/trade/dwd_trade_order_di.sql",
                               deps=[ids["ods_orders"], ids["dim_customer"], ids["hist"]], contract=True,
                               meta={"process": "order"},
                               columns={"order_id": "Order id.", "customer_key": "Customer durable key.",
                                        "order_amt": "Order amount.", "dt": "Partition date."})
    b.unique_combo(ids["dwd_order"], ["order_id", "dt"])
    b.not_null(ids["dwd_order"], "order_id")
    b.not_null(ids["dwd_order"], "dt")
    b.relationships(ids["dwd_order"], "customer_key", ids["dim_customer"], "customer_key")

    ids["dws_customer"] = b.model("dws_trade_customer_1d", "models/dws/trade/dws_trade_customer_1d.sql",
                                  deps=[ids["dwd_order"]], contract=True, meta={"grain": ["customer_key"]},
                                  columns={
                                      "customer_key": "Customer durable key.",
                                      "order_amt_sum_1d": {"description": "Order amount.", "meta": {"metric": "order_amt_sum_1d"}},
                                      "order_cnt_1d": {"description": "Orders.", "meta": {"metric": "order_cnt_1d"}},
                                      "dt": "Partition date.",
                                  })
    b.unique_combo(ids["dws_customer"], ["customer_key", "dt"])
    b.not_null(ids["dws_customer"], "customer_key")
    b.not_null(ids["dws_customer"], "dt")
    b.relationships(ids["dws_customer"], "customer_key", ids["dim_customer"], "customer_key")

    ids["ads_customer"] = b.model("ads_bi_customer_daily", "models/ads/bi/ads_bi_customer_daily.sql",
                                  deps=[ids["dws_customer"], ids["dim_customer"]],
                                  columns={
                                      "customer_key": "Customer durable key.",
                                      "city": "City.",
                                      "avg_order_amt_1d": {"description": "Average order amount.", "meta": {"metric": "avg_order_amt_1d"}},
                                      "dt": "Partition date.",
                                  })
    b.unique_combo(ids["ads_customer"], ["customer_key", "dt"])
    b.not_null(ids["ads_customer"], "customer_key")
    b.not_null(ids["ads_customer"], "dt")
    return b, ids
```

Replace `tools/dwh/tests/conftest.py` with:

```python
import itertools
import json

import pytest
from fixtures.warehouse import write_warehouse

from dwh.lint import Context, run_lint
from dwh.manifest import load_manifest
from dwh.warehouse import load_warehouse


@pytest.fixture
def make_warehouse(tmp_path):
    counter = itertools.count()

    def _make(mutate=None, drop=()):
        return write_warehouse(tmp_path / f"warehouse{next(counter)}", mutate=mutate, drop=drop)

    return _make


@pytest.fixture
def write_manifest(tmp_path):
    counter = itertools.count()

    def _write(builder):
        path = tmp_path / f"manifest{next(counter)}.json"
        path.write_text(json.dumps(builder.build()))
        return path

    return _write


@pytest.fixture
def lint(make_warehouse, write_manifest):
    """Lint `builder` against MINIMAL (after `mutate`); return finding codes, optionally by prefix."""

    def _lint(builder, mutate=None, prefix=None):
        ctx = Context(load_warehouse(make_warehouse(mutate=mutate)), load_manifest(write_manifest(builder)))
        return [f.code for f in run_lint(ctx) if prefix is None or f.code.startswith(prefix)]

    return _lint
```

- [ ] **Step 2: Write the failing loader, rule and CLI tests**

Create `tools/dwh/tests/test_manifest.py`:

```python
from fixtures.manifest import good_project

from dwh.manifest import load_manifest


def test_loads_models_snapshots_sources_and_tests(write_manifest):
    builder, ids = good_project()

    project = load_manifest(write_manifest(builder))

    assert {n.name for n in project.models()} == {
        "ods_shop_orders_di", "ods_shop_customers_df", "dim_pub_customer",
        "dwd_trade_order_di", "dws_trade_customer_1d", "ads_bi_customer_daily",
    }
    hist = project.nodes[ids["hist"]]
    assert hist.resource_type == "snapshot"
    assert hist.layer == "dim"
    assert project.nodes[ids["ods_orders"]].layer == "ods"
    assert project.nodes[ids["ods_orders"]].folder == "shop"
    assert [n.name for n in project.refs(project.nodes[ids["dwd_order"]])] == [
        "ods_shop_orders_di", "dim_pub_customer", "dim_pub_customer_hist",
    ]
    assert [s.name for s in project.source_deps(project.nodes[ids["ods_orders"]])] == ["orders"]
    assert len(project.tests_for(ids["dwd_order"])) == 4
    dws = project.nodes[ids["dws_customer"]]
    assert dws.columns["order_cnt_1d"].meta == {"metric": "order_cnt_1d"}
    assert dws.contract_enforced is True
    assert project.sources[ids["orders"]].meta["load"] == "di"


def test_ignores_nodes_from_other_packages(write_manifest):
    builder, ids = good_project()
    manifest = builder.build()
    foreign = dict(manifest["nodes"][ids["dim_customer"]], package_name="dbt_utils",
                   unique_id="model.dbt_utils.x", name="x")
    manifest["nodes"]["model.dbt_utils.x"] = foreign

    class Raw:
        def build(self):
            return manifest

    project = load_manifest(write_manifest(Raw()))

    assert "model.dbt_utils.x" not in project.nodes


def test_node_outside_a_layer_folder_has_no_layer(write_manifest):
    builder, _ = good_project()
    uid = builder.model("misc_model", "models/misc_model.sql")

    project = load_manifest(write_manifest(builder))

    assert project.nodes[uid].layer is None
```

Create `tools/dwh/tests/test_rules_docs.py`:

```python
from fixtures.manifest import good_project


def test_good_project_has_no_d_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-D") == []


def test_d01_model_without_description(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = "  "
    assert lint(builder, prefix="DWH-D") == ["DWH-D01"]


def test_d02_column_without_description(lint):
    builder, ids = good_project()
    builder.node(ids["dim_customer"])["columns"]["city"]["description"] = ""
    assert lint(builder, prefix="DWH-D") == ["DWH-D02"]


def test_d03_source_table_without_description(lint):
    builder, ids = good_project()
    builder.source_node(ids["orders"])["description"] = ""
    assert lint(builder, prefix="DWH-D") == ["DWH-D03"]
```

Create `tools/dwh/tests/test_rules_sources.py`:

```python
import pytest
from fixtures.manifest import good_project


def test_good_project_has_no_s_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-S") == []


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": None},
        {"timezone": "Mars/Base"},
        {"load": "hourly"},
        {"delete_handling": "ignore"},
        {"watermark": None},
    ],
)
def test_s01_incomplete_or_invalid_source_meta(lint, change):
    builder, ids = good_project()
    meta = builder.source_node(ids["orders"])["meta"]
    for key, value in change.items():
        if value is None:
            meta.pop(key)
        else:
            meta[key] = value
    assert lint(builder, prefix="DWH-S") == ["DWH-S01"]


def test_s01_df_source_needs_no_watermark(lint):
    builder, ids = good_project()
    assert "watermark" not in builder.source_node(ids["customers"])["meta"]
    assert lint(builder, prefix="DWH-S") == []


def test_s02_di_source_without_delete_handling_needs_a_reason(lint):
    builder, ids = good_project()
    builder.source_node(ids["orders"])["meta"]["delete_handling"] = "none"
    assert lint(builder, prefix="DWH-S") == ["DWH-S02"]

    builder.source_node(ids["orders"])["meta"]["delete_handling_reason"] = "Rows are never deleted."
    assert lint(builder, prefix="DWH-S") == []
```

Create `tools/dwh/tests/test_rules_testing.py`:

```python
from fixtures.manifest import good_project


def test_good_project_has_no_t_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-T") == []


def test_t01_model_without_grain_test(lint):
    builder, ids = good_project()
    for uid in builder.find_tests(ids["dim_customer"], "unique"):
        builder.remove(uid)
    assert lint(builder, prefix="DWH-T") == ["DWH-T01"]


def test_t02_grain_column_without_not_null(lint):
    builder, ids = good_project()
    for uid in builder.find_tests(ids["dws_customer"], "not_null", column="customer_key"):
        builder.remove(uid)
    assert lint(builder, prefix="DWH-T") == ["DWH-T02"]


def test_t03_contract_required_on_dim_dwd_dws(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["contract"]["enforced"] = False
    assert lint(builder, prefix="DWH-T") == ["DWH-T03"]


def test_t03_not_required_on_ods_and_ads(lint):
    builder, ids = good_project()
    assert builder.node(ids["ads_customer"])["contract"]["enforced"] is False
    assert builder.node(ids["ods_orders"])["contract"]["enforced"] is False
    assert lint(builder, prefix="DWH-T") == []


def test_t04_key_column_without_relationships_test(lint):
    builder, ids = good_project()
    for uid in builder.find_tests(ids["dwd_order"], "relationships"):
        builder.remove(uid)
    assert lint(builder, prefix="DWH-T") == ["DWH-T04"]
```

Create `tools/dwh/tests/test_lint.py`:

```python
from fixtures.manifest import good_project

from dwh.cli import main


def test_good_project_is_clean_for_every_family(lint):
    builder, _ = good_project()
    assert lint(builder) == []


def test_cli_lint_clean_exits_0(make_warehouse, write_manifest, capsys):
    builder, _ = good_project()

    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(write_manifest(builder))])

    assert rc == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"


def test_cli_lint_reports_findings_and_exits_1(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""

    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(write_manifest(builder))])

    out = capsys.readouterr().out
    assert rc == 1
    assert "models/dwd/trade/dwd_trade_order_di.sql: DWH-D01 dwd_trade_order_di: model has no description" in out


def test_cli_lint_select_filters_by_code_prefix(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""

    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(write_manifest(builder)),
               "--select", "DWH-T"])

    assert rc == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"


def test_cli_lint_runs_yaml_validation_first(make_warehouse, write_manifest, capsys):
    builder, _ = good_project()

    rc = main(["lint", "--warehouse", str(make_warehouse(drop=["glossary"])), "--manifest",
               str(write_manifest(builder))])

    assert rc == 1
    assert "DWH-Y01" in capsys.readouterr().out


def test_cli_lint_missing_manifest_exits_2(make_warehouse, tmp_path, capsys):
    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(tmp_path / "nope.json")])

    assert rc == 2
    assert "make manifest" in capsys.readouterr().err
```

Run: `make dwh-test`
Expected: FAIL. Collection errors: `No module named 'dwh.lint'` / `'dwh.manifest'`.

- [ ] **Step 3: Implement the manifest loader**

Create `tools/dwh/src/dwh/manifest.py`:

```python
"""The subset of dbt's manifest.json (schema v12) that the lint rules read."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

LAYERS = ("ods", "dim", "dwd", "dws", "ads")


@dataclass(frozen=True)
class Column:
    name: str
    description: str
    meta: dict


@dataclass(frozen=True)
class Node:
    """A model or a snapshot of the root project."""

    unique_id: str
    name: str
    resource_type: str
    path: str
    description: str
    meta: dict
    columns: dict[str, Column]
    depends_on: tuple[str, ...]
    contract_enforced: bool

    @property
    def layer(self) -> str | None:
        """models/<layer>/...; snapshots are DIM history tables (spec D11)."""
        if self.resource_type == "snapshot":
            return "dim"
        parts = PurePosixPath(self.path).parts
        if len(parts) >= 3 and parts[0] == "models" and parts[1] in LAYERS:
            return parts[1]
        return None

    @property
    def folder(self) -> str | None:
        """The folder under the layer: models/<layer>/<folder>/<file>."""
        parts = PurePosixPath(self.path).parts
        return parts[2] if len(parts) >= 4 and parts[0] == "models" else None


@dataclass(frozen=True)
class SourceTable:
    unique_id: str
    source_name: str
    name: str
    description: str
    meta: dict
    path: str


@dataclass(frozen=True)
class DataTest:
    unique_id: str
    name: str
    namespace: str | None
    attached_node: str | None
    column_name: str | None
    kwargs: dict


@dataclass(frozen=True)
class Project:
    nodes: dict[str, Node]
    sources: dict[str, SourceTable]
    tests: tuple[DataTest, ...]

    def models(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.resource_type == "model"]

    def refs(self, node: Node) -> list[Node]:
        return [self.nodes[d] for d in node.depends_on if d in self.nodes]

    def source_deps(self, node: Node) -> list[SourceTable]:
        return [self.sources[d] for d in node.depends_on if d in self.sources]

    def tests_for(self, unique_id: str) -> list[DataTest]:
        return [t for t in self.tests if t.attached_node == unique_id]


def load_manifest(path: Path) -> Project:
    manifest = json.loads(Path(path).read_text())
    project = manifest["metadata"]["project_name"]
    nodes: dict[str, Node] = {}
    tests: list[DataTest] = []
    for uid, raw in manifest["nodes"].items():
        if raw.get("package_name") != project:
            continue
        kind = raw["resource_type"]
        if kind in ("model", "snapshot"):
            nodes[uid] = Node(
                unique_id=uid,
                name=raw["name"],
                resource_type=kind,
                path=raw["original_file_path"],
                description=raw.get("description") or "",
                meta=raw.get("meta") or {},
                columns={
                    name: Column(name, c.get("description") or "", c.get("meta") or {})
                    for name, c in (raw.get("columns") or {}).items()
                },
                depends_on=tuple((raw.get("depends_on") or {}).get("nodes") or []),
                contract_enforced=bool((raw.get("contract") or {}).get("enforced")),
            )
        elif kind == "test" and raw.get("test_metadata"):
            meta = raw["test_metadata"]
            kwargs = meta.get("kwargs") or {}
            tests.append(
                DataTest(
                    unique_id=uid,
                    name=meta["name"],
                    namespace=meta.get("namespace"),
                    attached_node=raw.get("attached_node"),
                    column_name=raw.get("column_name") or kwargs.get("column_name"),
                    kwargs=kwargs,
                )
            )
    sources = {
        uid: SourceTable(
            unique_id=uid,
            source_name=raw["source_name"],
            name=raw["name"],
            description=raw.get("description") or "",
            meta=raw.get("meta") or {},
            path=raw["original_file_path"],
        )
        for uid, raw in manifest["sources"].items()
        if raw.get("package_name") == project
    }
    return Project(nodes, sources, tuple(tests))
```

- [ ] **Step 4: Implement the lint engine and families D, S, T**

Create `tools/dwh/src/dwh/lint.py`:

```python
"""Run lint rules over the warehouse design and the dbt manifest."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from dwh.findings import Finding
from dwh.manifest import Project
from dwh.warehouse import Warehouse


@dataclass(frozen=True)
class Context:
    warehouse: Warehouse
    project: Project


Rule = Callable[[Context], Iterable[Finding]]


def run_lint(ctx: Context, rules: Iterable[Rule] | None = None) -> list[Finding]:
    from dwh.rules import ALL_RULES  # rules import Context from this module

    selected = ALL_RULES if rules is None else list(rules)
    return sorted({finding for rule in selected for finding in rule(ctx)})
```

Create `tools/dwh/src/dwh/rules/__init__.py`:

```python
"""Lint rule families. Each module exposes RULES: functions `Context -> Iterable[Finding]`."""

from dwh.rules import docs, sources, testing

FAMILIES = (docs, sources, testing)
ALL_RULES = [rule for family in FAMILIES for rule in family.RULES]
```

Create `tools/dwh/src/dwh/rules/docs.py`:

```python
"""DWH-D: descriptions (spec §7, 09-dbt-conventions: every model and column is described)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context


def d01_model_description(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if not node.description.strip():
            yield Finding(node.path, "DWH-D01", f"{node.name}: model has no description")


def d02_column_description(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        for column in node.columns.values():
            if not column.description.strip():
                yield Finding(node.path, "DWH-D02", f"{node.name}.{column.name}: column has no description")


def d03_source_description(ctx: Context) -> Iterator[Finding]:
    for source in ctx.project.sources.values():
        if not source.description.strip():
            yield Finding(source.path, "DWH-D03", f"{source.source_name}.{source.name}: source table has no description")


RULES = [d01_model_description, d02_column_description, d03_source_description]
```

Create `tools/dwh/src/dwh/rules/sources.py`:

```python
"""DWH-S: source table metadata (spec §4: load type, watermark, timezone, delete handling)."""

from collections.abc import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dwh.findings import Finding
from dwh.lint import Context

LOADS = ("di", "df")
DELETE_HANDLING = ("none", "soft_delete_flag", "full_compare")


def is_timezone(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def s01_source_meta(ctx: Context) -> Iterator[Finding]:
    for source in ctx.project.sources.values():
        meta = source.meta
        problems = []
        if meta.get("load") not in LOADS:
            problems.append(f"meta.load must be one of {', '.join(LOADS)}, got {meta.get('load')!r}")
        if not is_timezone(meta.get("timezone")):
            problems.append(f"meta.timezone must be an IANA timezone, got {meta.get('timezone')!r}")
        if meta.get("delete_handling") not in DELETE_HANDLING:
            problems.append(
                f"meta.delete_handling must be one of {', '.join(DELETE_HANDLING)}, got {meta.get('delete_handling')!r}"
            )
        if meta.get("load") == "di" and not meta.get("watermark"):
            problems.append("meta.watermark is required for a di load")
        for problem in problems:
            yield Finding(source.path, "DWH-S01", f"{source.source_name}.{source.name}: {problem}")


def s02_di_without_delete_handling(ctx: Context) -> Iterator[Finding]:
    for source in ctx.project.sources.values():
        meta = source.meta
        if meta.get("load") == "di" and meta.get("delete_handling") == "none" and not meta.get("delete_handling_reason"):
            yield Finding(
                source.path,
                "DWH-S02",
                f"{source.source_name}.{source.name}: a di load cannot see hard deletes; set delete_handling "
                "or explain in meta.delete_handling_reason why rows are never deleted",
            )


RULES = [s01_source_meta, s02_di_without_delete_handling]
```

Create `tools/dwh/src/dwh/rules/testing.py`:

```python
"""DWH-T: minimum tests and contracts per layer (spec §7, 09-dbt-conventions)."""

from collections.abc import Iterable, Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.manifest import DataTest

CONTRACT_LAYERS = ("dim", "dwd", "dws")
KEY_RELATIONSHIP_LAYERS = ("dwd", "dws")


def is_uniqueness(test: DataTest) -> bool:
    return (test.name == "unique" and test.namespace is None) or (
        test.name == "unique_combination_of_columns" and test.namespace == "dbt_utils"
    )


def grain_columns(tests: Iterable[DataTest]) -> set[str]:
    columns: set[str] = set()
    for test in tests:
        if test.name == "unique" and test.namespace is None and test.column_name:
            columns.add(test.column_name)
        elif test.name == "unique_combination_of_columns" and test.namespace == "dbt_utils":
            columns.update(test.kwargs.get("combination_of_columns") or [])
    return columns


def t01_grain_test(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if not any(is_uniqueness(t) for t in ctx.project.tests_for(node.unique_id)):
            yield Finding(
                node.path, "DWH-T01", f"{node.name}: no grain test (unique or dbt_utils.unique_combination_of_columns)"
            )


def t02_grain_columns_not_null(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        tests = ctx.project.tests_for(node.unique_id)
        not_null = {t.column_name for t in tests if t.name == "not_null"}
        for column in sorted(grain_columns(tests) - not_null):
            yield Finding(node.path, "DWH-T02", f"{node.name}.{column}: grain column has no not_null test")


def t03_contract(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if node.layer in CONTRACT_LAYERS and not node.contract_enforced:
            yield Finding(node.path, "DWH-T03", f"{node.name}: {node.layer} models need contract: {{enforced: true}}")


def t04_key_relationships(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if node.layer not in KEY_RELATIONSHIP_LAYERS:
            continue
        related = {t.column_name for t in ctx.project.tests_for(node.unique_id) if t.name == "relationships"}
        for column in sorted(node.columns):
            if column.endswith("_key") and column not in related:
                yield Finding(
                    node.path, "DWH-T04", f"{node.name}.{column}: key column has no relationships test to its dimension"
                )


RULES = [t01_grain_test, t02_grain_columns_not_null, t03_contract, t04_key_relationships]
```

- [ ] **Step 5: Add `dwh lint` to the CLI**

In `tools/dwh/src/dwh/cli.py`:
- add these imports: `from dwh.lint import Context, run_lint`, `from dwh.manifest import load_manifest`,
  `from dwh.warehouse import load_warehouse`;
- add this function:

```python
def cmd_lint(args: argparse.Namespace) -> int:
    findings = validate(args.warehouse)
    if not findings:
        if not args.manifest.is_file():
            print(f"dwh: {args.manifest} not found; run `make manifest` first", file=sys.stderr)
            return 2
        findings = run_lint(Context(load_warehouse(args.warehouse), load_manifest(args.manifest)))
    if args.select:
        findings = [f for f in findings if f.code.startswith(tuple(args.select))]
    return report(findings)
```

and register it in `build_parser()` before `return parser`:

```python
    p = sub.add_parser("lint", help="lint the dbt project against the warehouse design")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--manifest", type=Path, default=Path(".dbt/target/manifest.json"))
    p.add_argument("--select", nargs="*", default=[], help="only report codes starting with these prefixes")
    p.set_defaults(func=cmd_lint)
```

- [ ] **Step 6: Add `make manifest` and `make dwh-lint`**

Add to the `Makefile` (and to `.PHONY`):

```make
# dbt on the host (no Docker, no Trino): same dbt versions as the image via requirements-dbt.txt.
HOST_DBT := uvx --python 3.12 --from dbt-core --with-requirements requirements-dbt.txt dbt
HOST_DBT_ENV := DBT_PROFILES_DIR=dags/dbt DBT_PACKAGES_INSTALL_PATH=$(CURDIR)/.dbt/packages \
	DBT_TARGET_PATH=$(CURDIR)/.dbt/target DBT_LOG_PATH=$(CURDIR)/.dbt/logs DBT_SEND_ANONYMOUS_USAGE_STATS=false

manifest:
	$(HOST_DBT_ENV) $(HOST_DBT) deps --project-dir dags/dbt
	$(HOST_DBT_ENV) $(HOST_DBT) parse --project-dir dags/dbt

dwh-lint: manifest
	$(DWH) lint --warehouse warehouse --manifest .dbt/target/manifest.json
```

- [ ] **Step 7: Run everything**

Run: `make dwh-test && make dwh-lint && make lint && git status --short`
Expected:
- dwh-test: all pass;
- dwh-lint ends with `0 finding(s)`: the real project has only the two ODS models, which pass D/S/T;
- lint clean;
- `git status` shows no changes under `dags/dbt`: `make manifest` must not write into the repository
  apart from `.dbt/`.

If dwh-lint reports findings on the real project, fix the project's YAML, not the rule, unless the rule
contradicts the spec. In that case stop and report.

- [ ] **Step 8: Commit**

```bash
git add tools/dwh Makefile
git commit -m "feat(dwh): add the manifest loader, dwh lint and rule families D, S and T" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Families N (naming) and L (layers)

**Files:**
- Create: `tools/dwh/src/dwh/rules/naming.py`, `tools/dwh/src/dwh/rules/layers.py`
- Modify: `tools/dwh/src/dwh/rules/__init__.py`
- Create: `tools/dwh/tests/test_rules_naming.py`, `tools/dwh/tests/test_rules_layers.py`

**Interfaces:**
- Consumes: Task 4 `Context`, `Node.layer`, `Node.folder`, `Project.refs`, `Project.source_deps`, `good_project`, `lint`.
- Produces:
  - `dwh.rules.naming.PERIODS`, `PATTERNS: dict[layer, re.Pattern]`, `parse_name(node) -> dict | None`.
    Task 6 uses `PATTERNS["dwd"]` and `PATTERNS["dws"]`.
  - `dwh.rules.layers.is_accumulating(ctx, node) -> bool`

- [ ] **Step 1: Write the failing tests**

Create `tools/dwh/tests/test_rules_naming.py`:

```python
from fixtures.manifest import good_project


def test_good_project_has_no_n_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-N") == []


def test_n01_dwd_name_without_load_suffix(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["name"] = "dwd_trade_order"
    assert lint(builder, prefix="DWH-N") == ["DWH-N01"]


def test_n01_ads_name_without_subject(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["name"] = "ads_bi"
    assert lint(builder, prefix="DWH-N") == ["DWH-N01"]


def test_n02_ods_source_segment_must_match_folder_and_source(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["name"] = "ods_crm_orders_di"
    assert lint(builder, prefix="DWH-N") == ["DWH-N02"]


def test_n03_dim_scope_must_be_pub_or_a_domain(lint):
    builder, ids = good_project()
    node = builder.node(ids["dim_customer"])
    node["name"], node["original_file_path"] = "dim_crm_customer", "models/dim/crm/dim_crm_customer.sql"
    # `crm` is also not a glossary word.
    assert lint(builder, prefix="DWH-N") == ["DWH-N03", "DWH-N05"]


def test_n04_snapshot_must_be_a_hist_table(lint):
    builder, ids = good_project()
    builder.node(ids["hist"])["name"] = "dim_pub_city"
    assert lint(builder, prefix="DWH-N") == ["DWH-N04"]


def test_n04_only_snapshots_produce_hist_tables(lint):
    builder, ids = good_project()
    builder.node(ids["dim_customer"])["name"] = "dim_pub_customer_hist"
    assert lint(builder, prefix="DWH-N") == ["DWH-N04"]


def test_n05_name_token_not_in_glossary(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["name"] = "dws_trade_buyer_segment_1d"
    assert lint(builder, prefix="DWH-N") == ["DWH-N05"]


def test_n06_column_token_not_in_glossary(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["order_segment"] = {
        "name": "order_segment", "description": "Segment.", "meta": {},
    }
    assert lint(builder, prefix="DWH-N") == ["DWH-N06"]


def test_ods_columns_are_exempt_from_the_glossary(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["columns"]["weird_col"] = {"name": "weird_col", "description": "X.", "meta": {}}
    assert lint(builder, prefix="DWH-N") == []
```

Create `tools/dwh/tests/test_rules_layers.py`:

```python
from fixtures.manifest import good_project


def test_good_project_has_no_l_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-L") == []


def test_l01_model_outside_a_layer_folder(lint):
    builder, ids = good_project()
    builder.model("stg_orders", "models/staging/stg_orders.sql", deps=[ids["ods_orders"]])
    assert lint(builder, prefix="DWH-L") == ["DWH-L01"]


def test_l02_name_prefix_must_match_the_layer_folder(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["name"] = "dws_bi_customer_daily"
    assert lint(builder, prefix="DWH-L") == ["DWH-L02"]


def test_l03_only_ods_reads_sources(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["depends_on"]["nodes"].append(ids["orders"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L03"]


def test_l03_ods_must_not_ref_models(lint):
    builder, ids = good_project()
    builder.node(ids["ods_orders"])["depends_on"]["nodes"].append(ids["ods_customers"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L03"]


def test_l04_dim_must_not_read_dwd(lint):
    builder, ids = good_project()
    builder.model("dim_pub_shop", "models/dim/pub/dim_pub_shop.sql", deps=[ids["dwd_order"]])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]


def test_l04_ads_may_read_dwd_only_with_a_written_reason(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["depends_on"]["nodes"].append(ids["dwd_order"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]

    builder.node(ids["ads_customer"])["meta"]["dwd_reason"] = "Order-level export for the finance app."
    assert lint(builder, prefix="DWH-L") == []


def test_l04_accumulating_snapshot_reads_transaction_facts_not_ods(lint):
    builder, ids = good_project()
    good = builder.model("dwd_trade_shipment_di", "models/dwd/trade/dwd_trade_shipment_di.sql",
                         deps=[ids["dwd_order"]], meta={"process": "shipment"})
    assert lint(builder, prefix="DWH-L") == []

    builder.node(good)["depends_on"]["nodes"].append(ids["ods_orders"])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]


def test_l04_snapshot_reads_ods_only(lint):
    builder, ids = good_project()
    builder.snapshot("dim_pub_shop_hist", "snapshots/dim_pub_shop_hist.yml", deps=[ids["dim_customer"]])
    assert lint(builder, prefix="DWH-L") == ["DWH-L04"]


def test_l05_chain_deeper_than_ten(lint):
    builder, ids = good_project()
    previous = ids["ods_customers"]
    for i in range(1, 12):  # dim chain of 11 models
        previous = builder.model(f"dim_pub_c{i}", f"models/dim/pub/dim_pub_c{i}.sql", deps=[previous])
    assert lint(builder, prefix="DWH-L") == ["DWH-L05"]
```

Run: `make dwh-test`
Expected: FAIL. The new "good project is clean" tests pass trivially and every defect test fails with
`[] == ['DWH-...']`.

- [ ] **Step 2: Implement `rules/naming.py`**

```python
"""DWH-N: model and column naming (spec §7, 02-naming)."""

import re
from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.manifest import LAYERS, Node

PERIODS = ("1d", "nd", "td", "1w", "hh", "mm")
_TOKENS = r"[a-z0-9]+(?:_[a-z0-9]+)*"

PATTERNS = {
    "ods": re.compile(rf"^ods_(?P<source>[a-z0-9]+)_(?P<table>{_TOKENS})_(?P<load>di|df)$"),
    "dim": re.compile(r"^dim_(?P<scope>[a-z0-9]+)_(?P<dimension>[a-z0-9]+(?:_[a-z0-9]+)*?)(?P<hist>_hist)?$"),
    "dwd": re.compile(rf"^dwd_(?P<domain>[a-z0-9]+)_(?P<process>{_TOKENS})_(?P<load>di|df)$"),
    "dws": re.compile(rf"^dws_(?P<domain>[a-z0-9]+)_(?P<grain>{_TOKENS})_(?P<period>{'|'.join(PERIODS)})$"),
    "ads": re.compile(rf"^ads_(?P<app>[a-z0-9]+)_(?P<subject>{_TOKENS})$"),
}
TEMPLATES = {
    "ods": "ods_{source}_{table}_{di|df}",
    "dim": "dim_{pub|domain}_{dimension}[_hist]",
    "dwd": "dwd_{domain}_{process}_{di|df}",
    "dws": "dws_{domain}_{grain}[_{custom}]_{1d|nd|td|1w|hh|mm}",
    "ads": "ads_{app}_{subject}",
}
GLOSSARY_LAYERS = ("dim", "dwd", "dws", "ads")
IGNORED_TOKENS = {*LAYERS, "di", "df", "pub", "hist", *PERIODS}
NUMERIC_PERIOD = re.compile(r"^\d+[dhmw]$")


def parse_name(node: Node) -> dict[str, str] | None:
    pattern = PATTERNS.get(node.layer or "")
    match = pattern.match(node.name) if pattern else None
    return match.groupdict() if match else None


def unknown_tokens(name: str, words: set[str]) -> list[str]:
    return [t for t in name.split("_") if t not in IGNORED_TOKENS and not NUMERIC_PERIOD.match(t) and t not in words]


def n01_name_pattern(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer and parse_name(node) is None:
            yield Finding(node.path, "DWH-N01", f"{node.name}: {node.layer} names follow {TEMPLATES[node.layer]}")


def n02_ods_source_segment(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        parsed = parse_name(node) if node.layer == "ods" else None
        if parsed is None:
            continue
        sources = {s.source_name for s in ctx.project.source_deps(node)}
        if parsed["source"] != node.folder or sources - {parsed["source"]}:
            yield Finding(
                node.path,
                "DWH-N02",
                f"{node.name}: source segment {parsed['source']!r} must match its folder models/ods/{node.folder}/ "
                "and the source() it reads",
            )


def n03_domain_segment(ctx: Context) -> Iterator[Finding]:
    domains = set(ctx.warehouse.domains)
    for node in ctx.project.nodes.values():
        parsed = parse_name(node)
        if parsed is None:
            continue
        if node.layer == "dim" and parsed["scope"] != "pub" and parsed["scope"] not in domains:
            yield Finding(node.path, "DWH-N03", f"{node.name}: scope {parsed['scope']!r} is neither pub nor a domain")
        elif node.layer in ("dwd", "dws") and parsed["domain"] not in domains:
            yield Finding(node.path, "DWH-N03", f"{node.name}: {parsed['domain']!r} is not a domain in domains.yml")


def n04_history_tables(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        parsed = parse_name(node) if node.layer == "dim" else None
        if parsed is None:
            continue
        if node.resource_type == "snapshot" and not parsed["hist"]:
            yield Finding(node.path, "DWH-N04", f"{node.name}: snapshots build SCD4 history tables named dim_..._hist")
        elif node.resource_type == "model" and parsed["hist"]:
            yield Finding(node.path, "DWH-N04", f"{node.name}: only snapshots produce _hist tables")


def n05_name_glossary(ctx: Context) -> Iterator[Finding]:
    words = ctx.warehouse.words
    for node in ctx.project.nodes.values():
        if node.layer in GLOSSARY_LAYERS:
            for token in unknown_tokens(node.name, words):
                yield Finding(node.path, "DWH-N05", f"{node.name}: {token!r} is not in glossary.yml")


def n06_column_glossary(ctx: Context) -> Iterator[Finding]:
    words = ctx.warehouse.words
    for node in ctx.project.nodes.values():
        if node.layer not in GLOSSARY_LAYERS:
            continue
        for column in node.columns:
            for token in unknown_tokens(column, words):
                yield Finding(node.path, "DWH-N06", f"{node.name}.{column}: {token!r} is not in glossary.yml")


RULES = [
    n01_name_pattern,
    n02_ods_source_segment,
    n03_domain_segment,
    n04_history_tables,
    n05_name_glossary,
    n06_column_glossary,
]
```

- [ ] **Step 3: Implement `rules/layers.py`**

```python
"""DWH-L: layer placement and dependency rules (spec §7, 01-layers)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.manifest import LAYERS, Node

ALLOWED = {
    "dim": frozenset({"ods", "dim"}),
    "dwd": frozenset({"ods", "dim"}),
    "dws": frozenset({"dwd", "dim", "dws"}),
    "ads": frozenset({"dws", "dim"}),
}
SNAPSHOT_ALLOWED = frozenset({"ods"})
CDM = ("dim", "dwd", "dws")
MAX_DEPTH = 10


def is_accumulating(ctx: Context, node: Node) -> bool:
    process = ctx.warehouse.processes.get(node.meta.get("process"))
    return bool(process) and process["fact_type"] == "accumulating_snapshot"


def l01_layer_folder(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer is None:
            yield Finding(node.path, "DWH-L01", f"{node.name}: models live under models/<{'|'.join(LAYERS)}>/")


def l02_prefix_matches_layer(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer and node.name.split("_", 1)[0] != node.layer:
            yield Finding(node.path, "DWH-L02", f"{node.name}: a {node.layer} model is named {node.layer}_...")


def l03_sources_only_in_ods(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer is None:
            continue
        sources, refs = ctx.project.source_deps(node), ctx.project.refs(node)
        if node.layer == "ods":
            if not sources:
                yield Finding(node.path, "DWH-L03", f"{node.name}: an ODS model reads a source()")
            for ref in refs:
                yield Finding(node.path, "DWH-L03", f"{node.name}: an ODS model must not ref {ref.name}")
        else:
            for source in sources:
                yield Finding(
                    node.path,
                    "DWH-L03",
                    f"{node.name}: only ODS models read source() ({source.source_name}.{source.name})",
                )


def l04_allowed_dependencies(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer in (None, "ods"):
            continue
        allowed = SNAPSHOT_ALLOWED if node.resource_type == "snapshot" else ALLOWED[node.layer]
        accumulating = node.layer == "dwd" and is_accumulating(ctx, node)
        for dep in ctx.project.refs(node):
            if dep.layer is None:
                continue  # reported by DWH-L01
            if accumulating and dep.layer == "ods":
                yield Finding(
                    node.path,
                    "DWH-L04",
                    f"{node.name}: an accumulating snapshot reads transaction facts (DWD), not ODS ({dep.name})",
                )
                continue
            ok = (
                dep.layer in allowed
                or (accumulating and dep.layer == "dwd")
                or (node.layer == "ads" and dep.layer == "dwd" and bool(node.meta.get("dwd_reason")))
            )
            if not ok:
                yield Finding(node.path, "DWH-L04", f"{node.name} ({node.layer}) must not read {dep.name} ({dep.layer})")


def l05_chain_depth(ctx: Context) -> Iterator[Finding]:
    depth: dict[str, int] = {}

    def chain(node: Node) -> int:
        if node.unique_id not in depth:
            parents = [d for d in ctx.project.refs(node) if d.layer in CDM]
            depth[node.unique_id] = 1 + max((chain(p) for p in parents), default=0)
        return depth[node.unique_id]

    for node in ctx.project.nodes.values():
        if node.layer in CDM and chain(node) > MAX_DEPTH:
            yield Finding(
                node.path,
                "DWH-L05",
                f"{node.name}: dependency chain inside DIM/DWD/DWS is {chain(node)} models deep (max {MAX_DEPTH})",
            )


RULES = [l01_layer_folder, l02_prefix_matches_layer, l03_sources_only_in_ods, l04_allowed_dependencies, l05_chain_depth]
```

- [ ] **Step 4: Register the families and run**

In `tools/dwh/src/dwh/rules/__init__.py`, change the import line to
`from dwh.rules import docs, layers, naming, sources, testing` and set
`FAMILIES = (docs, sources, testing, naming, layers)`.

Run: `make dwh-test && make dwh-lint && make lint`
Expected:
- all tests pass, including `test_good_project_is_clean_for_every_family`;
- dwh-lint: `0 finding(s)`;
- lint clean.

- [ ] **Step 5: Commit**

```bash
git add tools/dwh
git commit -m "feat(dwh): add lint rule families N (naming) and L (layers)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Families B (bus matrix) and M (metrics)

**Files:**
- Create: `tools/dwh/src/dwh/rules/bus.py`, `tools/dwh/src/dwh/rules/metrics.py`
- Modify: `tools/dwh/src/dwh/rules/__init__.py`
- Create: `tools/dwh/tests/test_rules_bus.py`, `tools/dwh/tests/test_rules_metrics.py`

**Interfaces:**
- Consumes:
  - Task 5 `PATTERNS`, `is_accumulating`
  - Task 3 `Warehouse.bus`, `.processes`, `.atomic`, `.derived`, `.calculated`
- Produces:
  - `dwh.rules.metrics.AGG_TOKEN: dict[str, str]`
  - `dwh.rules.metrics.metric_column(derived: dict, atomic: dict) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tools/dwh/tests/test_rules_bus.py`:

```python
from fixtures.manifest import good_project


def test_good_project_has_no_b_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-B") == []


def test_b01_dwd_without_process(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["meta"].pop("process")
    assert lint(builder, prefix="DWH-B") == ["DWH-B01"]


def test_b01_dwd_with_unknown_process(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["meta"]["process"] = "refund"
    assert lint(builder, prefix="DWH-B") == ["DWH-B01"]


def test_b02_dwd_name_must_match_its_process(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["meta"]["process"] = "shipment"
    assert lint(builder, prefix="DWH-B") == ["DWH-B02"]


def test_b03_process_must_have_a_bus_matrix_row(lint):
    builder, _ = good_project()

    def mutate(files):
        rows = files["bus_matrix"]["bus_matrix"]
        files["bus_matrix"]["bus_matrix"] = [r for r in rows if r["process"] != "order"]

    assert lint(builder, mutate=mutate, prefix="DWH-B") == ["DWH-B03"]


def test_b04_key_column_must_be_a_bus_matrix_dimension_or_role(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["seller_key"] = {"name": "seller_key", "description": "S.", "meta": {}}
    assert lint(builder, prefix="DWH-B") == ["DWH-B04"]


def test_b04_role_names_are_accepted(lint):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["columns"]["order_date_key"] = {
        "name": "order_date_key", "description": "Order date.", "meta": {},
    }
    assert lint(builder, prefix="DWH-B") == []
```

Create `tools/dwh/tests/test_rules_metrics.py`:

```python
import pytest
from fixtures.manifest import good_project

from dwh.rules.metrics import metric_column


@pytest.mark.parametrize(
    ("derived", "atomic", "expected"),
    [
        ({"period": "1d"}, {"name": "order_amt", "aggregation": "sum"}, "order_amt_sum_1d"),
        ({"period": "nd", "days": 30, "modifiers": ["app"]}, {"name": "order_amt", "aggregation": "sum"},
         "app_order_amt_sum_30d"),
        ({"period": "td"}, {"name": "order", "aggregation": "count"}, "order_cnt_td"),
        ({"period": "1d"}, {"name": "order_buyer", "aggregation": "count_distinct"}, "order_buyer_dcnt_1d"),
    ],
)
def test_metric_column_template(derived, atomic, expected):
    assert metric_column(derived, atomic) == expected


def column(name, metric):
    return {"name": name, "description": "A metric.", "meta": {"metric": metric}}


def test_good_project_has_no_m_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-M") == []


def test_m01_derived_metric_name_must_follow_the_template(lint):
    builder, _ = good_project()

    def mutate(files):
        files["metrics"]["derived"][1]["name"] = "app_order_amt_30d"

    assert lint(builder, mutate=mutate, prefix="DWH-M") == ["DWH-M01"]


def test_m02_derived_metric_on_a_non_additive_atomic(lint):
    builder, _ = good_project()

    def mutate(files):
        files["metrics"]["derived"].append({
            "name": "order_buyer_dcnt_1d", "atomic": "order_buyer", "period": "1d",
            "grain": ["customer"], "description": "Distinct buyers.",
        })

    assert lint(builder, mutate=mutate, prefix="DWH-M") == ["DWH-M02"]


def test_m03_dws_column_that_is_not_grain_dt_or_metric(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["city"] = {"name": "city", "description": "City.", "meta": {}}
    assert lint(builder, prefix="DWH-M") == ["DWH-M03"]


def test_m03_dws_must_declare_its_grain(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["meta"].pop("grain")
    # The model itself, and customer_key which is no longer a declared grain column.
    assert lint(builder, prefix="DWH-M") == ["DWH-M03", "DWH-M03"]


def test_m04_metric_column_must_be_named_after_its_metric(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["order_cnt_1d"]["meta"]["metric"] = "order_amt_sum_1d"
    assert lint(builder, prefix="DWH-M") == ["DWH-M04"]


def test_m04_ads_metric_must_exist(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["columns"]["avg_order_amt_1d"]["meta"]["metric"] = "avg_gmv_1d"
    assert lint(builder, prefix="DWH-M") == ["DWH-M04"]


def test_m05_one_period_per_dws_table(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["app_order_amt_sum_30d"] = column(
        "app_order_amt_sum_30d", "app_order_amt_sum_30d"
    )
    assert lint(builder, prefix="DWH-M") == ["DWH-M05"]


def test_m06_calculated_metric_must_not_be_stored_in_dws(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["avg_order_amt_1d"] = column("avg_order_amt_1d", "avg_order_amt_1d")
    assert lint(builder, prefix="DWH-M") == ["DWH-M06"]
```

Run: `make dwh-test`
Expected: FAIL. `ModuleNotFoundError: No module named 'dwh.rules.metrics'` at collection.

- [ ] **Step 2: Implement `rules/bus.py`**

```python
"""DWH-B: every DWD maps to a business process and its bus-matrix row (spec §5, §7 03)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.rules.naming import PATTERNS


def dwd_models(ctx: Context):
    return [n for n in ctx.project.models() if n.layer == "dwd"]


def b01_dwd_declares_a_process(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        process = node.meta.get("process")
        if not process:
            yield Finding(node.path, "DWH-B01", f"{node.name}: DWD models declare meta.process (from processes.yml)")
        elif process not in ctx.warehouse.processes:
            yield Finding(node.path, "DWH-B01", f"{node.name}: unknown process {process!r}")


def b02_dwd_name_matches_process(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        process = ctx.warehouse.processes.get(node.meta.get("process"))
        match = PATTERNS["dwd"].match(node.name)
        if process is None or match is None:
            continue
        if match["domain"] != process["domain"] or match["process"] != process["name"]:
            yield Finding(
                node.path,
                "DWH-B02",
                f"{node.name}: process {process['name']} of domain {process['domain']} is loaded into "
                f"dwd_{process['domain']}_{process['name']}_{{di|df}}",
            )


def b03_process_in_bus_matrix(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        process = node.meta.get("process")
        if process in ctx.warehouse.processes and process not in ctx.warehouse.bus:
            yield Finding(node.path, "DWH-B03", f"{node.name}: process {process} has no row in bus_matrix.yml")


def b04_keys_are_bus_dimensions(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        row = ctx.warehouse.bus.get(node.meta.get("process"))
        if row is None:
            continue
        allowed = {c["dimension"] for c in row["dimensions"]} | {c["role"] for c in row["dimensions"] if "role" in c}
        for column in sorted(node.columns):
            if column.endswith("_key") and column[: -len("_key")] not in allowed:
                yield Finding(
                    node.path,
                    "DWH-B04",
                    f"{node.name}.{column}: {column[: -len('_key')]!r} is not a dimension or role of process "
                    f"{row['process']} in bus_matrix.yml",
                )


RULES = [b01_dwd_declares_a_process, b02_dwd_name_matches_process, b03_process_in_bus_matrix, b04_keys_are_bus_dimensions]
```

- [ ] **Step 3: Implement `rules/metrics.py`**

```python
"""DWH-M: metric definitions and metric columns (spec §5, §7 06-metrics and 07-dws-ads)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.rules.naming import PATTERNS

AGG_TOKEN = {"sum": "sum", "count": "cnt", "count_distinct": "dcnt", "min": "min", "max": "max"}


def metric_column(derived: dict, atomic: dict) -> str:
    """{modifiers}_{atomic}_{agg}_{period}; an nd period renders as <days>d."""
    period = f"{derived['days']}d" if derived["period"] == "nd" else derived["period"]
    return "_".join([*derived.get("modifiers", []), atomic["name"], AGG_TOKEN[atomic["aggregation"]], period])


def m01_derived_name(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for derived in wh.derived.values():
        atomic = wh.atomic.get(derived["atomic"])
        if atomic is None:
            continue  # DWH-Y03
        expected = metric_column(derived, atomic)
        if derived["name"] != expected:
            yield Finding(
                wh.path("metrics"),
                "DWH-M01",
                f"derived metric {derived['name']}: name must be {expected} ({{modifiers}}_{{atomic}}_{{agg}}_{{period}})",
            )


def m02_no_derived_on_non_additive(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for derived in wh.derived.values():
        atomic = wh.atomic.get(derived["atomic"])
        if atomic and atomic["additivity"] == "non_additive":
            yield Finding(
                wh.path("metrics"),
                "DWH-M02",
                f"derived metric {derived['name']}: atomic metric {atomic['name']} is non-additive; store numerator and "
                "denominator as derived metrics and define the result as a calculated metric",
            )


def m03_dws_columns(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if node.layer != "dws":
            continue
        grain = node.meta.get("grain")
        if not isinstance(grain, list) or not grain:
            yield Finding(node.path, "DWH-M03", f"{node.name}: DWS models declare meta.grain (their grain columns)")
            grain = []
        for column in node.columns.values():
            if column.name in grain or column.name == "dt" or column.meta.get("metric"):
                continue
            yield Finding(
                node.path, "DWH-M03", f"{node.name}.{column.name}: DWS columns are grain columns, dt, or metrics (meta.metric)"
            )


def m04_metric_columns(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for node in ctx.project.models():
        if node.layer not in ("dws", "ads"):
            continue
        for column in node.columns.values():
            metric = column.meta.get("metric")
            if not metric:
                continue
            if node.layer == "dws" and metric in wh.calculated:
                continue  # DWH-M06
            known = wh.derived if node.layer == "dws" else {**wh.derived, **wh.calculated}
            if metric not in known:
                kind = "derived" if node.layer == "dws" else "derived or calculated"
                yield Finding(
                    node.path, "DWH-M04", f"{node.name}.{column.name}: meta.metric {metric!r} is not a {kind} metric"
                )
            elif column.name != metric:
                yield Finding(node.path, "DWH-M04", f"{node.name}.{column.name}: column must be named {metric}")


def m05_one_period_per_dws(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for node in ctx.project.models():
        match = PATTERNS["dws"].match(node.name) if node.layer == "dws" else None
        if match is None:
            continue
        for column in node.columns.values():
            derived = wh.derived.get(column.meta.get("metric"))
            if derived and derived["period"] != match["period"]:
                yield Finding(
                    node.path,
                    "DWH-M05",
                    f"{node.name}.{column.name}: metric period {derived['period']} differs from the table period "
                    f"{match['period']} (one statistical period per DWS table)",
                )


def m06_no_calculated_in_dwd_dws(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for node in ctx.project.models():
        if node.layer not in ("dwd", "dws"):
            continue
        for column in node.columns.values():
            metric = column.meta.get("metric")
            if metric in wh.calculated:
                yield Finding(
                    node.path,
                    "DWH-M06",
                    f"{node.name}.{column.name}: calculated metric {metric} must not be stored in {node.layer}; store "
                    "its inputs and compute it in ADS or BI",
                )


RULES = [
    m01_derived_name,
    m02_no_derived_on_non_additive,
    m03_dws_columns,
    m04_metric_columns,
    m05_one_period_per_dws,
    m06_no_calculated_in_dwd_dws,
]
```

- [ ] **Step 4: Register and run**

In `tools/dwh/src/dwh/rules/__init__.py`, import `bus` and `metrics` too and set
`FAMILIES = (docs, sources, testing, naming, layers, bus, metrics)`.

Run: `make dwh-test && make dwh-lint && make lint`
Expected:
- all tests pass, including `test_good_project_is_clean_for_every_family`, which now covers all
  families;
- dwh-lint: `0 finding(s)`;
- lint clean.

- [ ] **Step 5: Commit**

```bash
git add tools/dwh
git commit -m "feat(dwh): add lint rule families B (bus matrix) and M (metrics)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Design gate (`dwh design-gate`, DWH-G)

**Files:**
- Create: `tools/dwh/src/dwh/design_gate.py`, `tools/dwh/tests/test_design_gate.py`
- Modify: `tools/dwh/src/dwh/cli.py`
- Create: `.github/workflows/design-gate.yml`

**Interfaces:**
- Consumes: Task 3 `Warehouse`, `FILES`, `Finding`, `report`.
- Produces:
  - `dwh.design_gate.added_concepts(base: Warehouse, head: Warehouse) -> list[str]`
  - `dwh.design_gate.check_gate(added, *, body: str, labels: list[str], repo_root: Path) -> list[Finding]`
  - `dwh.design_gate.load_warehouse_at(ref: str, warehouse_rel: str, repo_root: Path) -> Warehouse`
  - CLI: `dwh design-gate --base REF --event FILE [--warehouse DIR] [--repo DIR]`

Spec §6.3: a PR that **adds** a domain, process, dimension or atomic metric must reference a
`docs/designs/…` record and carry the label `design-approved`.

- [ ] **Step 1: Write the failing tests**

Create `tools/dwh/tests/test_design_gate.py`:

```python
import copy
import json
import subprocess

import yaml
from fixtures.warehouse import MINIMAL, write_warehouse

from dwh.cli import main
from dwh.design_gate import added_concepts, check_gate, load_warehouse_at
from dwh.warehouse import Warehouse, load_warehouse


def warehouse(mutate=None) -> Warehouse:
    data = copy.deepcopy(MINIMAL)
    if mutate:
        mutate(data)
    return Warehouse(root=None, data=data)


def add_crm(files):
    files["domains"]["domains"].append({"name": "crm", "description": "CRM.", "owner": "data-eng"})
    files["processes"]["processes"].append({
        "name": "visit", "domain": "crm", "description": "A visit.", "fact_type": "transaction",
        "grain": "One row per visit.",
    })
    files["metrics"]["atomic"].append({
        "name": "visit", "process": "visit", "description": "Visits.", "aggregation": "count",
        "additivity": "additive",
    })


def test_added_concepts_lists_new_domains_processes_dimensions_and_atomic_metrics():
    assert added_concepts(warehouse(), warehouse(add_crm)) == ["domain crm", "process visit", "atomic metric visit"]


def test_reuse_changes_add_no_concepts():
    def add_derived(files):
        files["metrics"]["derived"].append({
            "name": "order_amt_sum_td", "atomic": "order_amt", "period": "td", "grain": ["customer"],
            "description": "Lifetime order amount.",
        })

    assert added_concepts(warehouse(), warehouse(add_derived)) == []


def test_gate_passes_with_label_and_existing_design_record(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "docs" / "designs" / "2026-11-05-crm.md").write_text("# CRM\n")

    findings = check_gate(["domain crm"], body="Design: docs/designs/2026-11-05-crm.md",
                          labels=["design-approved"], repo_root=tmp_path)

    assert findings == []


def test_gate_requires_the_label(tmp_path):
    (tmp_path / "docs" / "designs").mkdir(parents=True)
    (tmp_path / "docs" / "designs" / "x.md").write_text("# X\n")

    findings = check_gate(["domain crm"], body="docs/designs/x.md", labels=[], repo_root=tmp_path)

    assert [f.code for f in findings] == ["DWH-G01"]


def test_gate_requires_a_link_to_an_existing_design_record(tmp_path):
    findings = check_gate(["domain crm"], body="see docs/designs/missing.md", labels=["design-approved"],
                          repo_root=tmp_path)

    assert [f.code for f in findings] == ["DWH-G02"]


def test_gate_is_silent_without_additions(tmp_path):
    assert check_gate([], body="", labels=[], repo_root=tmp_path) == []


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


def test_load_warehouse_at_reads_the_base_commit_and_cli_end_to_end(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write_warehouse(repo / "warehouse")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    data = load_warehouse(repo / "warehouse").data
    add_crm(data)
    for name in ("domains", "processes", "metrics"):
        (repo / "warehouse" / f"{name}.yml").write_text(yaml.safe_dump(data[name], sort_keys=False))

    assert "crm" not in load_warehouse_at(base, "warehouse", repo).domains

    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": "no design", "labels": []}}))
    rc = main(["design-gate", "--base", base, "--event", str(event), "--warehouse", str(repo / "warehouse"),
               "--repo", str(repo)])

    out = capsys.readouterr().out
    assert rc == 1
    assert "DWH-G01" in out
    assert "DWH-G02" in out


def test_cli_rejects_an_unknown_base_ref(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write_warehouse(repo / "warehouse")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": "", "labels": []}}))

    rc = main(["design-gate", "--base", "no-such-ref", "--event", str(event), "--warehouse",
               str(repo / "warehouse"), "--repo", str(repo)])

    assert rc == 2
    assert "no-such-ref" in capsys.readouterr().err
```

Run: `make dwh-test`
Expected: FAIL. `No module named 'dwh.design_gate'`.

- [ ] **Step 2: Implement `design_gate.py`**

```python
"""Spec §6.3: a PR that adds a domain, process, dimension or atomic metric needs an approved design."""

import re
import subprocess
from pathlib import Path

import yaml

from dwh.findings import Finding
from dwh.warehouse import FILES, Warehouse

LABEL = "design-approved"
CONCEPTS = (
    ("domains", "domains", "domain"),
    ("processes", "processes", "process"),
    ("dimensions", "dimensions", "dimension"),
    ("metrics", "atomic", "atomic metric"),
)
DESIGN_LINK = re.compile(r"docs/designs/[\w./-]+?\.md")


def added_concepts(base: Warehouse, head: Warehouse) -> list[str]:
    added = []
    for file, key, label in CONCEPTS:
        new = [name for name in head.by_name(file, key) if name not in base.by_name(file, key)]
        added += [f"{label} {name}" for name in new]
    return added


def check_gate(added: list[str], *, body: str, labels: list[str], repo_root: Path) -> list[Finding]:
    if not added:
        return []
    what = ", ".join(added)
    findings = []
    if LABEL not in labels:
        findings.append(Finding("warehouse/", "DWH-G01", f"adds {what}: the PR needs the label {LABEL}"))
    links = [link for link in DESIGN_LINK.findall(body or "") if (repo_root / link).is_file()]
    if not links:
        findings.append(
            Finding("warehouse/", "DWH-G02", f"adds {what}: the PR description must link an existing docs/designs/*.md")
        )
    return findings


def load_warehouse_at(ref: str, warehouse_rel: str, repo_root: Path) -> Warehouse:
    """The warehouse YAML as of git `ref`. Raises ValueError for an unknown ref."""
    check = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise ValueError(f"unknown git ref {ref!r}")
    data = {}
    for name in FILES:
        shown = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{warehouse_rel}/{name}.yml"],
            capture_output=True,
            text=True,
            check=False,
        )
        data[name] = yaml.safe_load(shown.stdout) if shown.returncode == 0 else {}
    return Warehouse(repo_root / warehouse_rel, data)
```

- [ ] **Step 3: Add the CLI command**

In `tools/dwh/src/dwh/cli.py`, add `import json` and
`from dwh.design_gate import added_concepts, check_gate, load_warehouse_at`, then:

```python
def cmd_design_gate(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    warehouse_rel = args.warehouse.resolve().relative_to(repo).as_posix()
    try:
        base = load_warehouse_at(args.base, warehouse_rel, repo)
    except ValueError as exc:
        print(f"dwh: {exc}", file=sys.stderr)
        return 2
    event = json.loads(args.event.read_text())
    pull_request = event.get("pull_request") or {}
    labels = [label["name"] for label in pull_request.get("labels") or []]
    added = added_concepts(base, load_warehouse(args.warehouse))
    return report(check_gate(added, body=pull_request.get("body") or "", labels=labels, repo_root=repo))
```

Register it in `build_parser()`:

```python
    p = sub.add_parser("design-gate", help="require an approved design for model-extending changes")
    p.add_argument("--base", required=True, help="git ref of the PR base, e.g. origin/main")
    p.add_argument("--event", type=Path, required=True, help="GitHub event JSON ($GITHUB_EVENT_PATH)")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--repo", type=Path, default=Path("."))
    p.set_defaults(func=cmd_design_gate)
```

- [ ] **Step 4: Add the workflow**

Create `.github/workflows/design-gate.yml`:

```yaml
name: design-gate

# Separate from ci.yml so that adding or removing the design-approved label re-runs only this check.
on:
  pull_request:
    types: [opened, edited, reopened, synchronize, labeled, unlabeled]

permissions:
  contents: read

jobs:
  design-gate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - name: Model-extending changes need an approved design (spec §6.3)
        env:
          BASE_REF: ${{ github.base_ref }}
        run: uv run --locked --project tools/dwh dwh design-gate --base "origin/$BASE_REF" --event "$GITHUB_EVENT_PATH"
```

- [ ] **Step 5: Run and commit**

Run: `make dwh-test && make lint`
Expected: all pass.

```bash
git add tools/dwh .github/workflows/design-gate.yml
git commit -m "feat(dwh): add the design gate for model-extending warehouse changes" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Catalogue, GitHub Pages, CI wiring and docs

**Files:**
- Create: `tools/dwh/src/dwh/catalog.py`, `tools/dwh/tests/test_catalog.py`
- Modify: `tools/dwh/src/dwh/cli.py`, `Makefile`, `.github/workflows/ci.yml`
- Create: `.github/workflows/catalog.yml`
- Modify: `README.md`, `docs/en/specs/2026-11-04-kimball-dwh-design.md`

**Interfaces:**
- Consumes: Task 3 `Warehouse`, `validate`, `report`.
- Produces:
  - `dwh.catalog.render_catalog(wh: Warehouse, dbt_docs_link: str | None) -> str`
  - `dwh.catalog.write_catalog(wh: Warehouse, out: Path, dbt_docs: Path | None) -> Path`
  - CLI `dwh catalog --warehouse DIR --out DIR [--dbt-docs FILE]`; `make catalog`

- [ ] **Step 1: Write the failing tests**

Create `tools/dwh/tests/test_catalog.py`:

```python
from dwh.catalog import render_catalog, write_catalog
from dwh.cli import main
from dwh.warehouse import load_warehouse


def test_catalog_shows_bus_matrix_metrics_and_glossary(make_warehouse):
    page = render_catalog(load_warehouse(make_warehouse()), dbt_docs_link=None)

    assert "<th>customer</th>" in page
    assert "<td>order_date</td>" in page  # role name in the bus matrix cell
    assert "<td>app_order_amt_sum_30d</td>" in page
    assert "<td>nd (30 days)</td>" in page
    assert "<td>avg_order_amt_1d</td>" in page
    assert "dbt docs" not in page


def test_catalog_escapes_html(make_warehouse):
    def mutate(files):
        files["domains"]["domains"][0]["description"] = "<script>alert(1)</script>"

    page = render_catalog(load_warehouse(make_warehouse(mutate=mutate)), dbt_docs_link=None)

    assert "&lt;script&gt;" in page
    assert "<script>alert" not in page


def test_write_catalog_copies_and_links_dbt_docs(make_warehouse, tmp_path):
    docs = tmp_path / "static_index.html"
    docs.write_text("<html>dbt</html>")

    index = write_catalog(load_warehouse(make_warehouse()), tmp_path / "site", dbt_docs=docs)

    assert (tmp_path / "site" / "dbt" / "index.html").read_text() == "<html>dbt</html>"
    assert 'href="dbt/index.html"' in index.read_text()


def test_cli_catalog_writes_the_page(make_warehouse, tmp_path):
    rc = main(["catalog", "--warehouse", str(make_warehouse()), "--out", str(tmp_path / "site")])

    assert rc == 0
    assert (tmp_path / "site" / "index.html").is_file()


def test_cli_catalog_refuses_invalid_yaml(make_warehouse, tmp_path, capsys):
    rc = main(["catalog", "--warehouse", str(make_warehouse(drop=["periods"])), "--out", str(tmp_path / "site")])

    assert rc == 1
    assert "DWH-Y01" in capsys.readouterr().out
```

Run: `make dwh-test`
Expected: FAIL. `No module named 'dwh.catalog'`.

- [ ] **Step 2: Implement `catalog.py`**

```python
"""`dwh catalog`: one static HTML page of the design metadata (spec §5), linked to dbt docs."""

import html
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path

from dwh.warehouse import Warehouse

STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; padding: 0 1rem; }
table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; font-size: 0.9rem; }
th, td { border: 1px solid #d0d7de; padding: 0.35rem 0.6rem; text-align: left; vertical-align: top; }
th { background: #f6f8fa; }
nav a { margin-right: 1rem; }
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def bus_matrix(wh: Warehouse) -> str:
    dimensions = list(wh.dimensions)
    rows = []
    for process, row in wh.bus.items():
        cells: dict[str, list[str]] = {}
        for cell in row["dimensions"]:
            cells.setdefault(cell["dimension"], []).append(cell.get("role", "✓"))
        rows.append([process, *[", ".join(cells.get(d, [])) for d in dimensions]])
    return table(["process", *dimensions], rows)


def period_label(derived: dict) -> str:
    return f"nd ({derived['days']} days)" if derived["period"] == "nd" else derived["period"]


def render_catalog(wh: Warehouse, dbt_docs_link: str | None) -> str:
    sections = [
        ("Domains", table(["name", "owner", "description"],
                          [[d["name"], d["owner"], d["description"]] for d in wh.domains.values()])),
        ("Business processes", table(["name", "domain", "fact type", "grain", "description"],
                                     [[p["name"], p["domain"], p["fact_type"], p["grain"], p["description"]]
                                      for p in wh.processes.values()])),
        ("Dimensions", table(["name", "scope", "history", "natural key", "attributes"],
                             [[d["name"], d["scope"], d["history"], ", ".join(d["natural_key"]),
                               ", ".join(f"{a['name']} ({a['history']})" for a in d["attributes"])]
                              for d in wh.dimensions.values()])),
        ("Bus matrix", bus_matrix(wh)),
        ("Atomic metrics", table(["name", "process", "aggregation", "additivity", "description"],
                                 [[a["name"], a["process"], a["aggregation"], a["additivity"], a["description"]]
                                  for a in wh.atomic.values()])),
        ("Derived metrics", table(["column", "atomic", "period", "modifiers", "grain", "description"],
                                  [[d["name"], d["atomic"], period_label(d), ", ".join(d.get("modifiers", [])),
                                    ", ".join(d["grain"]), d["description"]] for d in wh.derived.values()])),
        ("Calculated metrics", table(["name", "formula", "inputs", "description"],
                                     [[c["name"], c["formula"], ", ".join(c["inputs"]), c["description"]]
                                      for c in wh.calculated.values()])),
        ("Modifiers", table(["name", "type", "predicate", "processes", "description"],
                            [[m["name"], m["type"], m["predicate"], ", ".join(m["processes"]), m["description"]]
                             for m in wh.modifiers.values()])),
        ("Glossary", table(["word", "meaning"],
                           [[w["word"], w["meaning"]] for w in wh.items("glossary", "words")])),
    ]
    anchors = [title.lower().replace(" ", "-") for title, _ in sections]
    nav = "".join(f'<a href="#{a}">{esc(t)}</a>' for a, (t, _) in zip(anchors, sections, strict=True))
    dbt = f'<p><a href="{esc(dbt_docs_link)}">dbt docs: models, columns and lineage</a></p>' if dbt_docs_link else ""
    body = "".join(f'<h2 id="{a}">{esc(t)}</h2>{content}' for a, (t, content) in zip(anchors, sections, strict=True))
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>example-dwh catalogue</title><style>{STYLE}</style></head>"
        f"<body><h1>example-dwh catalogue</h1><nav>{nav}</nav>{dbt}{body}</body></html>"
    )


def write_catalog(wh: Warehouse, out: Path, dbt_docs: Path | None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    link = None
    if dbt_docs is not None:
        (out / "dbt").mkdir(exist_ok=True)
        shutil.copyfile(dbt_docs, out / "dbt" / "index.html")
        link = "dbt/index.html"
    index = out / "index.html"
    index.write_text(render_catalog(wh, link))
    return index
```

- [ ] **Step 3: CLI, Makefile, workflows**

In `tools/dwh/src/dwh/cli.py`, add `from dwh.catalog import write_catalog` and:

```python
def cmd_catalog(args: argparse.Namespace) -> int:
    findings = validate(args.warehouse)
    if findings:
        return report(findings)
    index = write_catalog(load_warehouse(args.warehouse), args.out, args.dbt_docs)
    print(f"wrote {index}")
    return 0
```

Register it in `build_parser()`:

```python
    p = sub.add_parser("catalog", help="render the design catalogue as static HTML")
    p.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    p.add_argument("--out", type=Path, default=Path("site"))
    p.add_argument("--dbt-docs", type=Path, default=None, help="dbt's static_index.html to publish alongside")
    p.set_defaults(func=cmd_catalog)
```

Add to the `Makefile` (and to `.PHONY`):

```make
catalog: manifest
	$(HOST_DBT_ENV) $(HOST_DBT) docs generate --project-dir dags/dbt --no-compile --empty-catalog --static
	$(DWH) catalog --warehouse warehouse --out site --dbt-docs .dbt/target/static_index.html
```

In `.github/workflows/ci.yml`, the `lint` job's steps become:

```yaml
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - run: make lint
      - run: make test-repo
      - run: make dwh-test
      - run: make validate
      - run: make dwh-lint
```

Create `.github/workflows/catalog.yml`:

```yaml
name: catalog

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
      - run: make catalog
      - uses: actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d # v6.0.0
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-24.04
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346 # v5.0.1
```

- [ ] **Step 4: Docs**

In `README.md`, add a section `## Design metadata and lint` that lists:
- `make validate` (DWH-Y);
- `make dwh-lint`, which builds `.dbt/target/manifest.json` with host-side dbt via uv and runs all
  lint families;
- `make dwh-test`;
- `make catalog` (writes `site/`);
- `make lock`, which regenerates the image lock files after a change to `requirements*.txt`.

Also say that lint codes are `DWH-<family><nn>`, and list the families with one line each, copied
from this plan's Global Constraints.

In the spec `docs/en/specs/2026-11-04-kimball-dwh-design.md`:
- §8.1: after the `DWH-S*` bullet, add
  `- \`DWH-Y*\` warehouse YAML: JSON Schema (Y01) and cross-file consistency (Y02–Y06)`. In the
  "Design gate check (§6.3)" bullet, append `(\`dwh design-gate\`, codes \`DWH-G*\`, workflow
  \`design-gate.yml\`)`.
- §5: replace the sentence "Publishing target (GitHub Pages or internal host) is chosen during
  implementation of plan 2." with "It is published to GitHub Pages by `.github/workflows/catalog.yml`."
- §10: replace "Catalogue publishing target is decided in plan 2." with "Catalogue: GitHub Pages
  (plan 2)."
- §11: add one line `**Plan 2:** DWH-Y and DWH-G code families added; catalogue on GitHub Pages.`

- [ ] **Step 5: Run everything and commit**

Run:

```bash
bash -c 'set -o pipefail; make lint && make test-repo && make dwh-test && make validate && make dwh-lint \
  && make catalog && test -s site/index.html && test -s site/dbt/index.html; echo EXIT=$?'
```

Expected: `EXIT=0`. Then confirm with `git status --short` that `site/` and `.dbt/` are not listed
(both git-ignored).

```bash
git add tools/dwh Makefile .github/workflows README.md docs/en/specs/2026-11-04-kimball-dwh-design.md
git commit -m "feat(dwh): render the design catalogue and run dwh checks in CI" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Controller only: GitHub Pages**

Do not do this step as an implementer.

Turning on Pages changes repository settings, so it needs the user's approval. After approval, the
controller runs:

```bash
gh api -X POST repos/egret-data/example-dwh/pages -f build_type=workflow
```

The catalogue deploys on the first push to `main` after the plan 2 PR merges. Until Pages is turned on,
`catalog.yml`'s deploy job fails. That is expected, and it does not block the PR, because the workflow
runs only on `main`.

---

## Final verification (controller, before the final review)

On a fresh stack, at the branch head:

```bash
bash -c 'set -o pipefail; make dev-down && make lint && make test-repo && make dwh-test && make validate \
  && make dwh-lint && make catalog && make image && make dev-up && make smoke && make test-dags \
  && make test-integration && make e2e; echo EXIT=$?' 2>&1 | tee /tmp/plan2-final-chain.log | tail -40
```

Expected: `EXIT=0`. Then re-record `docs/en/verification/` with a new file
`<date>-plan2-verification.md` (the date of the run). It lists each command, its result, the head commit, and these
plan-specific checks:

- V1: the e2e row check for logical date 2026-11-03 gives `dt` 2026-11-02 = 2 orders.
- V2: the two dbt unit tests run inside the ODS build.
- V3: ODS timestamps are `timestamp(6) with time zone`.
- V4: the image installs only from the lock files, with `--no-deps`, and `pip check` passes.
- V5: `dwh lint` on the real project reports 0 findings, and every rule has a failing test (list the
  test names per code).
- V6: the design gate fails without the label or the design link (unit tests), and the workflow
  triggers on label events.
