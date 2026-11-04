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
