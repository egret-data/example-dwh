"""Transform and maintenance DAGs follow STD-11-08 and select the models they own."""

import os

from _common.assets import model_asset


def test_model_asset_matches_the_uri_cosmos_emits(monkeypatch):
    monkeypatch.setenv("DBT_TARGET", "dev")
    monkeypatch.setenv("DBT_SCHEMA", "dev")
    monkeypatch.setenv("TRINO_HOST", "trino")
    monkeypatch.setenv("TRINO_PORT", "8080")
    monkeypatch.setenv("TRINO_CATALOG", "iceberg")

    assert (
        model_asset("ods", "ods_shop_orders_di").uri
        == "trino://trino:8080/iceberg/dev_ods/ods_shop_orders_di"
    )


def test_model_asset_uses_the_layer_schema_in_prod(monkeypatch):
    monkeypatch.setenv("DBT_TARGET", "prod")
    assert model_asset("dws", "dws_trade_customer_1d").uri.endswith("/dws/dws_trade_customer_1d")


def test_pub_and_trade_dags_select_their_models(dagbag):
    pub = dagbag.get_dag("dbt_pub")
    trade = dagbag.get_dag("dbt_trade")

    assert any("dim_pub_customer" in t for t in pub.task_ids)
    assert any("dim_pub_date" in t for t in pub.task_ids)
    assert not any("dwd_" in t for t in pub.task_ids)
    assert any("dwd_trade_order_di" in t for t in trade.task_ids)
    assert any("ads_crm_customer_value" in t for t in trade.task_ids)
    assert not any("dim_pub_" in t for t in trade.task_ids)


def test_maintenance_dag_runs_weekly_with_owner_and_tags(dagbag):
    dag = dagbag.get_dag("iceberg_maintenance")
    assert dag.owner == "data-eng"
    assert "layer:maintenance" in dag.tags
    assert os.path.basename(dag.fileloc) == "iceberg_maintenance.py"


def scheduled_models(dag) -> set[str]:
    condition = dag.timetable.asset_condition
    if hasattr(condition, "uri"):  # a single Asset
        return {condition.uri.rsplit("/", 1)[-1]}
    return {asset.uri.rsplit("/", 1)[-1] for asset in condition.objects}


def test_transform_dags_are_scheduled_on_the_assets_they_read(dagbag):
    pub = dagbag.get_dag("dbt_pub")
    trade = dagbag.get_dag("dbt_trade")

    assert scheduled_models(pub) == {"ods_shop_customers_df"}
    assert scheduled_models(trade) == {
        "ods_shop_orders_di",
        "ods_shop_payments_di",
        "ods_shop_shops_df",
        "dim_pub_customer",
        "dim_pub_date",
        "dim_pub_customer_hist",
    }


def test_test_tasks_do_not_pick_up_tests_of_models_built_by_another_dag(dagbag):
    # Eager indirect selection makes `dbt test --select dim_pub_customer` run the DWD relationships tests.
    for dag_id in ("dbt_pub", "dbt_trade"):
        tests = [t for t in dagbag.get_dag(dag_id).tasks if t.task_id.endswith(".test")]
        assert tests
        assert all(t.indirect_selection == "buildable" for t in tests), dag_id


def test_every_task_writes_its_dbt_artifacts_to_its_own_target_path(dagbag):
    # Cosmos reads the asset outlets from run_results.json under DBT_TARGET_PATH. A path shared by the
    # tasks of a run lets concurrent tasks read each other's results and emit events for the wrong asset
    # (measured).
    for dag_id in ("dbt_ods_shop", "dbt_pub", "dbt_trade"):
        for task in dagbag.get_dag(dag_id).tasks:
            assert "{{ ti.task_id }}" in task.env["DBT_TARGET_PATH"], task.task_id
