import pytest
import yaml

from dwh.cli import main
from dwh.scaffold import ScaffoldError, scaffold, write_files
from dwh.warehouse import load_warehouse
from fixtures.manifest import good_project

TODAY = "date '{{ get_dt() }}'"


@pytest.fixture
def wh(make_warehouse):
    return load_warehouse(make_warehouse())


def model_of(text):
    return yaml.safe_load(text)["models"][0]


def columns(model):
    return {c["name"]: c for c in model["columns"]}


def add_to_project(builder, files, deps):
    """Register scaffolded models in a ManifestBuilder the way dbt would parse them, descriptions filled."""
    for path, text in files.items():
        if not path.endswith(".yml") or path.startswith("snapshots/"):
            continue
        model = model_of(text)
        config = model.get("config", {})
        uid = builder.model(
            model["name"],
            path.removesuffix(".yml") + ".sql",
            deps=deps,
            columns={
                c["name"]: {"description": "Filled in.", "meta": c.get("config", {}).get("meta", {})}
                for c in model["columns"]
            },
            meta=config.get("meta", {}),
            contract=config.get("contract", {}).get("enforced", False),
        )
        for column in model["columns"]:
            for test in column.get("data_tests", []):
                if test in ("unique", "not_null"):
                    builder.test(test, uid, column=column["name"])
                else:
                    arguments = test["relationships"]["arguments"]
                    builder.test("relationships", uid, column=column["name"], **arguments)
        for test in model.get("data_tests", []):
            combo = test["dbt_utils.unique_combination_of_columns"]["arguments"]["combination_of_columns"]
            builder.unique_combo(uid, combo)


def test_ods_di_replaces_the_partition_for_the_vietnam_day(wh):
    files = scaffold("ods_shop_orders_di", wh, project_dir="", grain=["order_id"])

    assert set(files) == {"models/ods/shop/ods_shop_orders_di.sql", "models/ods/shop/ods_shop_orders_di.yml"}
    sql = files["models/ods/shop/ods_shop_orders_di.sql"]
    assert "source_timezone('shop', 'orders')" in sql
    assert "source('shop', 'orders')" in sql
    assert "in_business_day('updated_at', tz)" in sql
    assert "incremental_strategy='append'" in sql
    model = model_of(files["models/ods/shop/ods_shop_orders_di.yml"])
    assert model["description"] == ""
    assert model["data_tests"] == [
        {
            "dbt_utils.unique_combination_of_columns": {
                "arguments": {"combination_of_columns": ["order_id", "dt"]}
            }
        }
    ]
    assert columns(model)["order_id"]["data_tests"] == ["not_null"]


def test_ods_df_has_no_day_window(wh):
    files = scaffold("ods_shop_customers_df", wh, project_dir="", grain=["customer_id"])
    assert "in_business_day" not in files["models/ods/shop/ods_shop_customers_df.sql"]


def test_project_dir_prefixes_every_path(wh):
    files = scaffold("ods_shop_orders_di", wh, grain=["order_id"])
    assert "dags/dbt/models/ods/shop/ods_shop_orders_di.sql" in files


def test_scd4_dimension_comes_with_its_hist_snapshot(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])

    model = model_of(files["models/dim/pub/dim_pub_customer.yml"])
    assert model["config"]["contract"] == {"enforced": True}
    key = columns(model)["customer_key"]
    assert key["data_tests"] == ["unique", "not_null"]
    assert key["data_type"] == "varchar"
    assert (
        "generate_surrogate_key(['customer_id']) }} as customer_key"
        in files["models/dim/pub/dim_pub_customer.sql"]
    )
    snapshot = yaml.safe_load(files["snapshots/dim_pub_customer_hist.yml"])["snapshots"][0]
    assert snapshot["relation"] == "ref('dim_pub_customer')"
    assert snapshot["config"]["unique_key"] == ["customer_key"]
    assert snapshot["config"]["strategy"] == "check"
    assert snapshot["config"]["check_cols"] == ["city"]
    assert snapshot["config"]["snapshot_meta_column_names"] == {
        "dbt_valid_from": "valid_from",
        "dbt_valid_to": "valid_to",
    }


def test_scd1_dimension_has_no_snapshot(wh):
    files = scaffold("dim_trade_shop", wh, project_dir="", upstream=["ods_shop_customers_df"])
    assert set(files) == {"models/dim/trade/dim_trade_shop.sql", "models/dim/trade/dim_trade_shop.yml"}


@pytest.mark.parametrize(
    ("name", "kwargs", "message"),
    [
        ("dim_pub_shop", {"upstream": ["x"]}, "scope trade"),
        ("dim_pub_store", {"upstream": ["x"]}, "not in warehouse/dimensions.yml"),
        ("dim_pub_customer_hist", {"upstream": ["x"]}, "snapshots"),
        (
            "dwd_trade_refund_di",
            {"upstream": ["x"], "grain": ["refund_id"]},
            "not in warehouse/processes.yml",
        ),
        (
            "dws_trade_customer_1d",
            {"upstream": ["x"], "grain": ["customer_key"], "metrics": ["app_order_amt_sum_30d"]},
            "period nd",
        ),
        (
            "dws_trade_customer_1d",
            {"upstream": ["x"], "grain": ["customer_key"], "metrics": ["gmv_1d"]},
            "not a derived metric",
        ),
        ("fact_orders", {}, "must start with"),
        ("dwd_trade_order_di", {"upstream": ["x"]}, "--grain is required"),
        ("dwd_trade_order_di", {"grain": ["order_id"]}, "--from is required"),
    ],
)
def test_scaffold_refuses_what_the_design_does_not_allow(wh, name, kwargs, message):
    with pytest.raises(ScaffoldError, match=message):
        scaffold(name, wh, project_dir="", **kwargs)


def test_scaffolded_dwd_passes_every_lint_family(wh, lint):
    builder, ids = good_project()
    files = scaffold(
        "dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["ods_shop_orders_di"]
    )

    model = model_of(files["models/dwd/trade/dwd_trade_order_di.yml"])
    assert model["config"]["meta"] == {"process": "order"}
    assert columns(model)["order_date_key"]["data_tests"] == [
        {"relationships": {"arguments": {"to": "ref('dim_pub_date')", "field": "date_key"}}}
    ]
    add_to_project(builder, files, deps=[ids["ods_orders"], ids["dim_customer"]])
    assert lint(builder) == []


def test_scaffolded_dws_passes_every_lint_family(wh, lint):
    builder, ids = good_project()
    files = scaffold(
        "dws_trade_customer_1d",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=["order_amt_sum_1d", "order_cnt_1d"],
        upstream=["dwd_trade_order_di"],
    )

    sql = files["models/dws/trade/dws_trade_customer_1d.sql"]
    assert f"sum(order_amt) filter (where dt = {TODAY}) as order_amt_sum_1d" in sql
    assert f"count(*) filter (where dt = {TODAY}) as order_cnt_1d" in sql
    add_to_project(builder, files, deps=[ids["dwd_order"]])
    assert lint(builder) == []


def test_nd_metric_filters_by_modifier_and_window(wh):
    files = scaffold(
        "dws_trade_customer_nd",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=["app_order_amt_sum_30d"],
        upstream=["dwd_trade_order_di"],
    )

    expected = f"sum(order_amt) filter (where channel = 'app' and dt > {TODAY} - interval '30' day)"
    assert f"{expected} as app_order_amt_sum_30d" in files["models/dws/trade/dws_trade_customer_nd.sql"]


def test_scaffolded_ads_writes_calculated_metrics_as_formulas_and_lints_clean(wh, lint):
    builder, ids = good_project()
    files = scaffold(
        "ads_bi_customer_daily",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=["order_amt_sum_1d", "avg_order_amt_1d"],
        upstream=["dws_trade_customer_1d"],
    )

    assert (
        "order_amt_sum_1d / order_cnt_1d as avg_order_amt_1d"
        in files["models/ads/bi/ads_bi_customer_daily.sql"]
    )
    add_to_project(builder, files, deps=[ids["dws_customer"]])
    assert lint(builder) == []


def test_write_files_refuses_to_overwrite(tmp_path):
    files = {"a/b.sql": "select 1\n"}

    assert write_files(files, tmp_path) == ["a/b.sql"]
    with pytest.raises(ScaffoldError, match="refusing to overwrite"):
        write_files(files, tmp_path)


def test_cli_scaffold_prints_writes_and_rejects(make_warehouse, capsys, tmp_path, monkeypatch):
    warehouse = str(make_warehouse())
    monkeypatch.chdir(tmp_path)

    assert main(["scaffold", "ods_shop_orders_di", "--grain", "order_id", "--warehouse", warehouse]) == 0
    assert "# dags/dbt/models/ods/shop/ods_shop_orders_di.sql" in capsys.readouterr().out
    assert not (tmp_path / "dags").exists()

    args = ["scaffold", "ods_shop_orders_di", "--grain", "order_id", "--warehouse", warehouse, "--write"]
    assert main(args) == 0
    assert (tmp_path / "dags/dbt/models/ods/shop/ods_shop_orders_di.yml").is_file()

    assert (
        main(["scaffold", "dwd_trade_refund_di", "--grain", "x", "--from", "y", "--warehouse", warehouse])
        == 2
    )
