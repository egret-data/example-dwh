"""Airflow DAG: build the shared dimensions (dim_pub_*) and their _hist snapshots."""

from cosmos import DbtDag

from _common.assets import model_asset
from _common.dates import ASSET_DT_TEMPLATE, vn_date
from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS

dbt_pub = DbtDag(
    dag_id="dbt_pub",
    schedule=model_asset("ods", "ods_shop_customers_df"),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:dim", "domain:pub"],
    **dbt_dag_kwargs(select=["tag:domain:pub"], dt_template=ASSET_DT_TEMPLATE),
)
