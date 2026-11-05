"""Airflow DAG: weekly Iceberg maintenance, retention deletes then optimize and snapshot expiry."""

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from airflow.timetables.trigger import CronTriggerTimetable

from _common.dates import BUSINESS_TZ, vn_date
from _common.dbt import DBT_EXECUTABLE, DBT_PROJECT_DIR, DBT_TARGET
from _common.defaults import DEFAULT_ARGS

with DAG(
    dag_id="iceberg_maintenance",
    schedule=CronTriggerTimetable("0 3 * * 0", timezone=BUSINESS_TZ),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:maintenance"],
) as dag:
    BashOperator(
        task_id="run_operation",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && {DBT_EXECUTABLE} run-operation iceberg_maintenance "
            "--args '{dry_run: false}' --target " + DBT_TARGET
        ),
        env={"DBT_TARGET_PATH": "/tmp/dbt/target-maintenance", "DBT_LOG_PATH": "/tmp/dbt/logs"},
        append_env=True,
    )
