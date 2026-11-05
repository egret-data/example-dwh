"""Airflow DAG: build the trade domain (DIM, DWD, DWS) and the CRM customer-value ADS."""

from cosmos import DbtDag

from _common.assets import model_asset
from _common.dates import ASSET_DT_TEMPLATE, vn_date
from _common.dbt import dbt_dag_kwargs
from _common.defaults import DEFAULT_ARGS

dbt_trade = DbtDag(
    dag_id="dbt_trade",
    schedule=(
        model_asset("ods", "ods_shop_orders_di")
        & model_asset("ods", "ods_shop_payments_di")
        & model_asset("ods", "ods_shop_shops_df")
        & model_asset("dim", "dim_pub_customer")
        & model_asset("dim", "dim_pub_date")
        & model_asset("dim", "dim_pub_customer_hist")  # Cosmos emits an Asset for a snapshot too (measured)
    ),
    start_date=vn_date(2026, 11, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["layer:dwd", "layer:dws", "layer:ads", "domain:trade"],
    **dbt_dag_kwargs(select=["tag:domain:trade", "tag:app:crm"], dt_template=ASSET_DT_TEMPLATE),
)
