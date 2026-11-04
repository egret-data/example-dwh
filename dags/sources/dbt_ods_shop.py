"""Airflow DAG: load source system `shop` into ODS (Iceberg) for the logical date."""

from datetime import datetime

from cosmos import DbtDag

from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS

dbt_ods_shop = DbtDag(
    dag_id="dbt_ods_shop",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:ods", "source:shop"],
    **dbt_dag_kwargs(select=["tag:ods_shop"]),
)
