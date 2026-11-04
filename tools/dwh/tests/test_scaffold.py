import re

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
    assert snapshot["config"]["strategy"] == "timestamp"
    assert snapshot["config"]["updated_at"] == "updated_at"
    assert "check_cols" not in snapshot["config"]
    assert snapshot["config"]["snapshot_meta_column_names"] == {
        "dbt_valid_from": "valid_from",
        "dbt_valid_to": "valid_to",
    }


def test_scd1_dimension_has_no_snapshot(wh):
    files = scaffold("dim_trade_shop", wh, project_dir="", upstream=["ods_shop_customers_df"])
    assert set(files) == {"models/dim/trade/dim_trade_shop.sql", "models/dim/trade/dim_trade_shop.yml"}
    assert "updated_at" not in files["models/dim/trade/dim_trade_shop.sql"]
    assert "updated_at" not in columns(model_of(files["models/dim/trade/dim_trade_shop.yml"]))


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
        "dwd_trade_order_di",
        wh,
        project_dir="",
        grain=["order_id"],
        upstream=["ods_shop_orders_di"],
        event_at="created_at",
    )

    sql = files["models/dwd/trade/dwd_trade_order_di.sql"]
    assert "with versions as (" in sql
    assert "row_number() over (partition by order_id order by dt) as version_rank" in sql
    assert "where version_rank = 1\n" in sql
    assert f"dt >= {TODAY}" in sql
    assert "{{ in_business_day_tz('created_at') }}" in sql
    assert "select *" not in sql
    model = model_of(files["models/dwd/trade/dwd_trade_order_di.yml"])
    assert model["config"]["meta"] == {"process": "order"}
    assert model["config"]["tags"] == ["domain:trade"]
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
    assert re.search(r"sum\(order_amt\)\s+as order_amt_sum_1d", sql)
    assert re.search(r"count\(\*\)\s+as order_cnt_1d", sql)
    assert "filter" not in sql
    assert f"where dt = {TODAY}\n" in sql
    assert "group by customer_key\n" in sql
    add_to_project(builder, files, deps=[ids["dwd_order"]])
    assert lint(builder) == []


def test_nd_metric_filters_by_modifier_and_the_window_goes_in_where(wh):
    files = scaffold(
        "dws_trade_customer_nd",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=["app_order_amt_sum_30d"],
        upstream=["dwd_trade_order_di"],
    )

    sql = files["models/dws/trade/dws_trade_customer_nd.sql"]
    assert re.search(
        r"sum\(order_amt\) filter \(\s*where channel = 'app'\s*\)\s+as app_order_amt_sum_30d", sql
    )
    assert f"where dt > {TODAY} - interval '30' day\n" in sql


@pytest.mark.parametrize(
    ("name", "metrics", "where"),
    [
        ("dws_trade_customer_1w", ["order_amt_sum_1w"], f"dt > {TODAY} - interval '7' day"),
        ("dws_trade_customer_td", ["order_amt_sum_td"], f"dt <= {TODAY}"),
    ],
)
def test_other_periods_put_their_window_in_where(make_warehouse, name, metrics, where):
    def add_metric(files):
        files["metrics"]["derived"].append(
            {
                "name": metrics[0],
                "atomic": "order_amt",
                "period": name.rsplit("_", 1)[1],
                "grain": ["customer"],
                "description": "Order amount.",
            }
        )

    warehouse = load_warehouse(make_warehouse(mutate=add_metric))
    files = scaffold(name, warehouse, project_dir="", grain=["customer_key"], metrics=metrics, upstream=["x"])
    sql = files[f"models/dws/trade/{name}.sql"]
    assert f"where {where}\n" in sql
    assert "filter" not in sql


def test_dwd_hashes_the_role_column_or_the_natural_key(wh):
    order = scaffold(
        "dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["x"], event_at="created_at"
    )
    sql = order["models/dwd/trade/dwd_trade_order_di.sql"]
    assert "generate_surrogate_key(['order_date'])" not in sql
    assert re.search(
        r"when customer_id is null then '-1'\s+"
        r"else \{\{ dbt_utils.generate_surrogate_key\(\['customer_id'\]\) \}\}"
        r"\s+end\s+as customer_key",
        sql,
    )
    assert (
        "-- Durable keys: hash of the dimension's natural key (a role hashes its own column, e.g. ship_date;"
        in sql
    )
    assert "a single date role is derived from the event column)" in sql


def test_event_dwd_with_two_date_roles_hashes_each_role_column(make_warehouse):
    def add_ship_date(files):
        files["bus_matrix"]["bus_matrix"][0]["dimensions"].append({"dimension": "date", "role": "ship_date"})

    wh = load_warehouse(make_warehouse(mutate=add_ship_date))
    sql = scaffold(
        "dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["x"], event_at="created_at"
    )["models/dwd/trade/dwd_trade_order_di.sql"]

    assert "generate_surrogate_key(['order_date'])" in sql
    assert "generate_surrogate_key(['ship_date'])" in sql
    assert "Asia/Ho_Chi_Minh" not in sql
    versions = sql.split("with versions as (", 1)[1].split("from {{ ref('x') }}", 1)[0]
    for name in ("order_date", "ship_date"):
        assert re.search(rf"^\s+{name},$", versions, re.MULTILINE), name


def test_dwd_maps_a_null_natural_key_to_the_unknown_member(wh):
    files = scaffold(
        "dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["x"], event_at="created_at"
    )
    sql = files["models/dwd/trade/dwd_trade_order_di.sql"]
    for key, natural in [("customer_key", "customer_id")]:
        case = (
            f"    case\n"
            f"        when {natural} is null then '-1'\n"
            f"        else {{{{ dbt_utils.generate_surrogate_key(['{natural}']) }}}}\n"
            f"    end"
        )
        assert re.search(rf"{re.escape(case)}\s+as {key},", sql), key
    # The versions CTE lists each key's source column, the event column and dt, nothing else.
    versions = sql.split("with versions as (", 1)[1].split("from {{ ref('x') }}", 1)[0]
    for name in ("order_id", "customer_id", "shop_id", "created_at", "dt"):
        assert re.search(rf"^\s+{name},$", versions, re.MULTILINE), name


def test_special_members_carry_text_labels(wh):
    sql = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])[
        "models/dim/pub/dim_pub_customer.sql"
    ]
    assert "'Unknown'" in sql
    assert "'Not applicable'" in sql
    assert "timestamp '1900-01-01 00:00:00 UTC'" in sql


def test_scd4_dimension_carries_updated_at_and_snapshots_by_timestamp(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])

    model = model_of(files["models/dim/pub/dim_pub_customer.yml"])
    assert columns(model)["updated_at"]["data_type"] == "timestamp(6) with time zone"
    snapshot = yaml.safe_load(files["snapshots/dim_pub_customer_hist.yml"])["snapshots"][0]
    assert snapshot["config"]["strategy"] == "timestamp"
    assert snapshot["config"]["updated_at"] == "updated_at"
    assert "check_cols" not in snapshot["config"]


def test_event_dwd_derives_its_single_date_role_from_the_event_column(wh):
    sql = scaffold(
        "dwd_trade_order_di",
        wh,
        project_dir="",
        grain=["order_id"],
        upstream=["ods_shop_orders_di"],
        event_at="created_at",
    )["models/dwd/trade/dwd_trade_order_di.sql"]

    assert re.search(
        r"case\s+when created_at is null then '-1'\s+else \{\{ dbt_utils.generate_surrogate_key\(\s*"
        r"\[\"cast\(created_at at time zone 'Asia/Ho_Chi_Minh' as date\)\"\]\s*\) \}\}"
        r"\s+end\s+as order_date_key",
        sql,
    )
    assert "['order_date']" not in sql


def test_accumulating_snapshot_dwd_is_written_by_hand(wh):
    with pytest.raises(ScaffoldError, match="write accumulating snapshots by hand: merge milestone events"):
        scaffold(
            "dwd_trade_shipment_di", wh, project_dir="", grain=["order_id"], upstream=["x"], event_at="x_at"
        )


def test_transaction_dwd_requires_the_event_column(wh):
    with pytest.raises(ScaffoldError, match="--event-at is required"):
        scaffold("dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["x"])


def test_dimension_unions_the_special_members_with_a_null_natural_key(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])

    sql = files["models/dim/pub/dim_pub_customer.sql"]
    assert "special_members as (" in sql
    assert re.search(r"'-1'\s+as customer_key", sql)
    assert re.search(r"'-2'\s+as customer_key", sql)
    assert re.search(r"cast\(null as bigint\)\s+as customer_id", sql)
    assert re.search(r"'Unknown'\s+as city", sql)
    assert re.search(r"'Not applicable'\s+as city", sql)
    assert "union all" in sql
    assert "select *" not in sql
    model = model_of(files["models/dim/pub/dim_pub_customer.yml"])
    assert columns(model)["customer_id"]["data_tests"] == [
        {"not_null": {"config": {"where": "customer_key not in ('-1', '-2')"}}}
    ]


def test_dimension_from_a_df_upstream_reads_its_latest_partition(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_df"])

    sql = files["models/dim/pub/dim_pub_customer.sql"]
    assert "where dt = (select max(dt) from {{ ref('ods_shop_customers_df') }})" in sql
    assert "row_number()" not in sql


def test_dimension_from_a_di_upstream_keeps_the_latest_version_per_natural_key(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_di"])

    sql = files["models/dim/pub/dim_pub_customer.sql"]
    assert "row_number() over (partition by customer_id order by dt desc) as version_rank" in sql
    assert "where version_rank = 1\n" in sql
    assert "max(dt)" not in sql


@pytest.mark.parametrize(
    ("name", "kwargs", "path", "tags"),
    [
        ("dim_pub_customer", {"upstream": ["x_df"]}, "models/dim/pub/dim_pub_customer.yml", ["domain:pub"]),
        ("dim_trade_shop", {"upstream": ["x_df"]}, "models/dim/trade/dim_trade_shop.yml", ["domain:trade"]),
        (
            "dws_trade_customer_1d",
            {"grain": ["customer_key"], "metrics": ["order_cnt_1d"], "upstream": ["x"]},
            "models/dws/trade/dws_trade_customer_1d.yml",
            ["domain:trade"],
        ),
        (
            "ads_bi_customer_daily",
            {"grain": ["customer_key"], "metrics": ["order_cnt_1d"], "upstream": ["x"]},
            "models/ads/bi/ads_bi_customer_daily.yml",
            ["app:bi"],
        ),
    ],
)
def test_every_scaffolded_model_after_ods_carries_its_selection_tag(wh, name, kwargs, path, tags):
    files = scaffold(name, wh, project_dir="", **kwargs)
    assert model_of(files[path])["config"]["tags"] == tags


def test_the_hist_snapshot_runs_with_its_dimension(wh):
    files = scaffold("dim_pub_customer", wh, project_dir="", upstream=["x_df"])
    snapshot = yaml.safe_load(files["snapshots/dim_pub_customer_hist.yml"])["snapshots"][0]
    assert snapshot["config"]["tags"] == ["domain:pub"]


def test_scd4_without_a_historical_attribute_is_refused(make_warehouse):
    def make_current(files):
        files["dimensions"]["dimensions"][1]["attributes"][0]["history"] = "current"

    warehouse = load_warehouse(make_warehouse(mutate=make_current))
    with pytest.raises(ScaffoldError, match="at least one historical attribute"):
        scaffold("dim_pub_customer", warehouse, project_dir="", upstream=["x"])


@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("ods_shop_orders_di", {"grain": ["order_id"]}),
        ("dim_pub_customer", {"upstream": ["x"]}),
        ("dwd_trade_order_di", {"grain": ["order_id"], "upstream": ["x"], "event_at": "created_at"}),
        (
            "dws_trade_customer_1d",
            {"grain": ["customer_key"], "metrics": ["order_cnt_1d"], "upstream": ["x"]},
        ),
        (
            "ads_bi_customer_daily",
            {"grain": ["customer_key"], "metrics": ["order_cnt_1d"], "upstream": ["x"]},
        ),
    ],
)
def test_descriptions_are_empty_so_that_d01_d02_fail_until_filled(wh, name, kwargs):
    files = scaffold(name, wh, project_dir="", **kwargs)
    for path, text in files.items():
        if path.endswith(".yml"):
            body = yaml.safe_load(text)
            entry = (body.get("models") or body["snapshots"])[0]
            assert entry["description"] == ""
            assert all(c["description"] == "" for c in entry.get("columns", []))


def test_no_generated_line_is_longer_than_110_rendered_characters(wh):
    files = scaffold(
        "dws_trade_customer_nd",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=["app_order_amt_sum_30d"],
        upstream=["dwd_trade_order_di"],
    )
    files |= scaffold(
        "dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["x"], event_at="created_at"
    )
    files |= scaffold("dim_pub_customer", wh, project_dir="", upstream=["ods_shop_customers_di"])
    for path, text in files.items():
        if path.endswith(".sql"):
            for line in text.replace("{{ get_dt() }}", "2026-11-02").splitlines():
                assert len(line) <= 110, line
                assert "noqa" not in line
                assert "sqlfluff:" not in line


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
        "order_amt_sum_1d / nullif(order_cnt_1d, 0) as avg_order_amt_1d"
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

    dwd = ["scaffold", "dwd_trade_order_di", "--grain", "order_id", "--from", "ods_shop_orders_di"]
    assert main([*dwd, "--warehouse", warehouse]) == 2
    assert "--event-at is required" in capsys.readouterr().err
    assert main([*dwd, "--event-at", "created_at", "--warehouse", warehouse]) == 0
    assert "in_business_day_tz('created_at')" in capsys.readouterr().out


def depends_on_lines(sql: str) -> list[str]:
    return [line for line in sql.splitlines() if line.startswith("-- depends_on:")]


def test_dwd_declares_every_dimension_its_relationships_tests_point_to(wh):
    # Without a ref() the dimension is no ancestor, so `--indirect-selection buildable` drops the tests.
    sql = scaffold(
        "dwd_trade_order_di", wh, project_dir="", grain=["order_id"], upstream=["x"], event_at="created_at"
    )["models/dwd/trade/dwd_trade_order_di.sql"]

    assert depends_on_lines(sql) == [
        "-- depends_on: {{ ref('dim_pub_customer') }}",
        "-- depends_on: {{ ref('dim_pub_date') }}",
        "-- depends_on: {{ ref('dim_trade_shop') }}",
    ]


def test_dws_declares_the_dimensions_of_its_grain_keys(wh):
    sql = scaffold(
        "dws_trade_customer_1d",
        wh,
        project_dir="",
        grain=["customer_key"],
        upstream=["dwd_trade_order_di"],
        metrics=["order_amt_sum_1d"],
    )["models/dws/trade/dws_trade_customer_1d.sql"]

    assert depends_on_lines(sql) == ["-- depends_on: {{ ref('dim_pub_customer') }}"]
