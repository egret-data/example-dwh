# 11 — Airflow DAGs

Scope: DAG files under `dags/`. The examples import from `_common` the way `dags/sources/dbt_ods_shop.py` does.

## Rules

### STD-11-01 One DAG per source or domain (MUST)

Each source system has one DAG, `dags/sources/dbt_ods_<source>.py`, which loads that source into ODS. Each domain has
one DAG, `dags/transform/dbt_<domain>.py`, which builds DIM, DWD and DWS for that domain. The `dag_id` equals the file
name without the extension.

Correct:

```text
dags/sources/dbt_ods_shop.py      dag_id="dbt_ods_shop"
dags/transform/dbt_trade.py       dag_id="dbt_trade"
```

Incorrect:

```text
dags/all_models.py                dag_id="everything"   # one DAG for every layer and source
```

Source: Spec §3

### STD-11-02 Cosmos DbtDag (MUST)

A DAG is a `cosmos.DbtDag` built with the keyword arguments of `_common.dbt.dbt_dag_kwargs(select=[...])`, so every
DAG shares one profile, executable and project path. `select` uses tags (STD-09-04), not file paths. Cosmos renders
one Airflow task per dbt node and emits an Asset for each.

Correct:

```python
from cosmos import DbtDag

from _common.dbt import dbt_dag_kwargs

dag = DbtDag(dag_id="dbt_ods_shop", **dbt_dag_kwargs(select=["tag:ods_shop"]))
```

Incorrect:

```python
from airflow.providers.standard.operators.bash import BashOperator

run = BashOperator(task_id="dbt_run", bash_command="dbt run")  # one opaque task, own paths and profile
```

Source: Spec §4

### STD-11-03 Business-day schedule (MUST)

Use `schedule=daily_vn()` and `start_date=vn_date(...)` from `_common.dates`. `daily_vn()` fires at 00:00
Asia/Ho_Chi_Minh, and each run covers the previous Vietnam day. The dt reaches dbt only through `DT_TEMPLATE`, which
`dbt_dag_kwargs` already passes as `operator_args`; a DAG does not build its own. `conf.dt` of a manual run or
backfill overrides the day. A DAG scheduled on Assets has no cron interval of its own, so it passes
`dt_template=ASSET_DT_TEMPLATE`, which takes the day from the triggering `dbt_ods_*` run; `dbt_pub` and `dbt_trade`
do this. A manual run of such a DAG must pass `conf.dt`.

Correct:

```python
from cosmos import DbtDag

from _common.dates import daily_vn, vn_date
from _common.dbt import dbt_dag_kwargs

dag = DbtDag(
    dag_id="dbt_ods_shop",
    schedule=daily_vn(),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
```

Incorrect:

```python
from cosmos import DbtDag

from _common.dbt import dbt_dag_kwargs

dag = DbtDag(
    dag_id="dbt_ods_shop",
    schedule="0 0 * * *",  # midnight UTC, not midnight in Vietnam
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
```

Source: Spec §4

### STD-11-04 Assets, not sensors (MUST)

A DAG that depends on another schedules on the Airflow Assets that Cosmos emits for the models it reads. It does
not poll with a sensor. Asset URIs contain the schema of the environment (`<target.schema>_ods` in dev, `ods` in
prod), so the same code is correct in each environment and a dev run never triggers prod. Prod uses `ods` where the
example has `dev_ods`. That an event on an asset no DAG consumed yet triggers a consumer is unmeasured (plan 4).

Correct:

```python
from airflow.sdk import Asset

orders = Asset("trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di")
schedule = [orders]
```

Incorrect:

```python
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor

wait = ExternalTaskSensor(task_id="wait_ods", external_dag_id="dbt_ods_shop")  # polls, and ignores the dt
```

Source: Spec §4

### STD-11-05 Owner, retries and tags (MUST)

Set `default_args=DEFAULT_ARGS` from `_common.defaults`, so every DAG has the same owner, retry count and retry
delay. Tag each DAG with `layer:*` and with `source:*` or `domain:*`. The retries matter: STD-08-04 relies on a retry
to restore a partition.

Correct:

```python
from cosmos import DbtDag

from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS

dag = DbtDag(
    dag_id="dbt_ods_shop",
    default_args=DEFAULT_ARGS,
    tags=["layer:ods", "source:shop"],
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
```

Incorrect:

```python
from cosmos import DbtDag

from _common.dbt import dbt_dag_kwargs

dag = DbtDag(
    dag_id="dbt_ods_shop",
    default_args={"owner": "airflow", "retries": 0},  # a hand-written copy: no retry restores a partition
    tags=["layer:ods", "source:shop"],
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
```

Source: Spec §8.1

### STD-11-06 The word airflow (MUST)

Each DAG file contains the word `airflow`, for example in its module docstring. The DAG processor's safe mode skips
a file that lacks the words `airflow` and `dag`. A Cosmos DAG file need not import from `airflow`, so the docstring
is what carries the word. A skipped file raises no error: the DAG is just missing.

Correct:

```python
"""Airflow DAG: load source system `shop` into ODS (Iceberg) for the Vietnam business day."""
```

Incorrect:

```python
"""Load source system `shop` into ODS."""  # no "airflow": safe mode may skip the file silently
```

Source: Spec §11

### STD-11-07 Read-only code volume (MUST)

The code volume is read-only at runtime. Nothing writes into the repository: dbt `target/` and logs go to `/tmp`, and
packages are baked into the image. A DAG never installs dbt packages, so `dbt_dag_kwargs` sets `install_dbt_deps` to
false. The packages directory comes from `DBT_PACKAGES_INSTALL_PATH`. git-sync checks the repository out at
`/opt/airflow/dags/repo`, and the dbt project is `dags/dbt` inside it (`_common/dbt.py`).

Correct:

```python
from cosmos import ProjectConfig

project = ProjectConfig(dbt_project_path="/opt/airflow/dags/repo/dags/dbt", install_dbt_deps=False)
```

Incorrect:

```python
from cosmos import ProjectConfig

# install_dbt_deps=True writes dbt_packages into the read-only volume
project = ProjectConfig(dbt_project_path="/opt/airflow/dags/repo/dags/dbt", install_dbt_deps=True)
```

Source: Spec §3

### STD-11-08 Every model has a DAG (MUST)

Every model and snapshot runs in exactly one DAG, chosen by its selection tag (STD-09-04). `dim_pub_*` and their
`_hist` snapshots run in `dags/transform/dbt_pub.py`, which selects `tag:domain:pub` and is scheduled on the ODS
Assets it reads. Domain models run in `dbt_<domain>`, which selects `tag:domain:<domain>` and is scheduled on the
Assets it reads (STD-11-04). Snapshots run every day, before the DWD that joins them; inside one DAG, dbt's `ref()`
order does this, and across DAGs `dbt_trade` also waits on the Asset Cosmos emits for the snapshot. A missed snapshot day loses those versions for good, because a backfill cannot recreate history:
monitor that each snapshot ran.

Correct:

```python
"""Airflow DAG: build the shared dimensions (dim_pub_*) and their _hist snapshots."""

from airflow.sdk import Asset
from cosmos import DbtDag

from _common.dates import vn_date
from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS

dbt_pub = DbtDag(
    dag_id="dbt_pub",
    schedule=[Asset("trino://trino:8080/iceberg/dev_ods/ods_shop_customers_df")],
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:dim", "domain:pub"],
    **dbt_dag_kwargs(select=["tag:domain:pub"]),
)
```

Incorrect:

```text
dim_pub_customer and dim_pub_customer_hist have no domain tag, so no DAG selects them   # they never run
```

Source: Spec §4
