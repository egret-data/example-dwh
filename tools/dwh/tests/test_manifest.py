from dwh.manifest import load_manifest
from fixtures.manifest import good_project


def test_loads_models_snapshots_sources_and_tests(write_manifest):
    builder, ids = good_project()

    project = load_manifest(write_manifest(builder))

    assert {n.name for n in project.models()} == {
        "ods_shop_orders_di",
        "ods_shop_customers_df",
        "dim_pub_customer",
        "dwd_trade_order_di",
        "dws_trade_customer_1d",
        "ads_bi_customer_daily",
    }
    hist = project.nodes[ids["hist"]]
    assert hist.resource_type == "snapshot"
    assert hist.layer == "dim"
    assert project.nodes[ids["ods_orders"]].layer == "ods"
    assert project.nodes[ids["ods_orders"]].folder == "shop"
    assert [n.name for n in project.refs(project.nodes[ids["dwd_order"]])] == [
        "ods_shop_orders_di",
        "dim_pub_customer",
        "dim_pub_customer_hist",
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
    foreign = dict(
        manifest["nodes"][ids["dim_customer"]],
        package_name="dbt_utils",
        unique_id="model.dbt_utils.x",
        name="x",
    )
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


def test_project_dir_is_joined_onto_paths_and_layers_still_resolve(write_manifest):
    builder, ids = good_project()

    project = load_manifest(write_manifest(builder), "dags/dbt")

    node = project.nodes[ids["ods_orders"]]
    assert node.path == "dags/dbt/models/ods/shop/ods_shop_orders_di.sql"
    assert (node.layer, node.folder) == ("ods", "shop")
    assert project.sources[ids["orders"]].path.startswith("dags/dbt/")
