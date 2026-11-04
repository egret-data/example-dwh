"""Every DAG in dags/ imports cleanly and follows the minimum conventions."""


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


def test_every_dag_has_a_real_owner_and_tags(dagbag):
    assert dagbag.dags, "no DAGs found"
    for dag_id, dag in dagbag.dags.items():
        assert dag.owner not in ("", "airflow"), f"{dag_id} has no owner"
        assert dag.tags, f"{dag_id} has no tags"


def test_ods_shop_dag_renders_only_shop_ods_models(dagbag):
    dag = dagbag.get_dag("dbt_ods_shop")

    assert dag is not None
    task_ids = set(dag.task_ids)
    assert any("ods_shop_orders_di" in t for t in task_ids)
    assert any("ods_shop_customers_df" in t for t in task_ids)
    assert all("ods_shop" in t for t in task_ids), task_ids
