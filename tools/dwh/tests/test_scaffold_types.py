"""`dwh scaffold` takes a passed-through column's type from what the upstream model outputs (M-2)."""

import os
import re
from pathlib import Path

import pytest
import yaml

from dwh.cli import main
from dwh.column_types import ColumnTypeError, ColumnTypes, load_column_types, ods_casts
from dwh.scaffold import ScaffoldError, metric_type, scaffold
from dwh.warehouse import load_warehouse

REPO = Path(__file__).resolve().parents[3]
ORDERS_SQL = """select
    cast(order_id as {order_id}) as order_id,
    {{{{ source_ts('created_at', tz) }}}} as created_at,
    date '{{{{ get_dt() }}}}' as dt
from {{{{ source('shop', 'orders') }}}}
"""


@pytest.fixture
def wh(make_warehouse):
    return load_warehouse(make_warehouse())


def write_yml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def ods_project(root: Path, *, yml_type=None, sql_type=None, source_type=None) -> Path:
    """A dbt project with ods_shop_orders_di; order_id typed in its .yml, its .sql cast, or its source."""
    order_id: dict = {"name": "order_id", "description": "Order id."}
    if yml_type:
        order_id["data_type"] = yml_type
    write_yml(
        root / "models/ods/shop/_shop__models.yml",
        {"version": 2, "models": [{"name": "ods_shop_orders_di", "columns": [order_id]}]},
    )
    if source_type:
        column = {
            "name": "order_id",
            "data_type": source_type,
            "config": {"meta": {"data_type": source_type}},
        }
        write_yml(
            root / "models/ods/shop/_shop__sources.yml",
            {
                "version": 2,
                "sources": [{"name": "shop", "tables": [{"name": "orders", "columns": [column]}]}],
            },
        )
    if sql_type:
        (root / "models/ods/shop/ods_shop_orders_di.sql").write_text(ORDERS_SQL.format(order_id=sql_type))
    return root


def dwd_order(wh, types, upstream=("ods_shop_orders_di",)):
    return scaffold(
        "dwd_trade_order_di",
        wh,
        project_dir="",
        grain=["order_id"],
        upstream=list(upstream),
        event_at="created_at",
        column_types=types,
    )["models/dwd/trade/dwd_trade_order_di.yml"]


def column_type(text: str, name: str) -> str:
    model = yaml.safe_load(text)["models"][0]
    return {c["name"]: c for c in model["columns"]}[name]["data_type"]


def guess_comment(text: str) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if "guessed" in line)


# --- reading the project ---


def test_load_column_types_reads_model_declarations_and_ods_casts(tmp_path):
    project = ods_project(tmp_path, yml_type="varchar", sql_type="bigint")

    types = load_column_types(project)

    assert types.models["ods_shop_orders_di"]["order_id"] == "varchar"
    assert types.ods_casts["ods_shop_orders_di"] == {
        "order_id": "bigint",
        "created_at": "timestamp(6) with time zone",
        "dt": "date",
    }


def test_snapshot_declarations_are_read(tmp_path):
    write_yml(
        tmp_path / "snapshots/dim_pub_customer_hist.yml",
        {
            "snapshots": [
                {"name": "dim_pub_customer_hist", "columns": [{"name": "city", "data_type": "varchar"}]}
            ]
        },
    )

    assert load_column_types(tmp_path).upstream_type(["dim_pub_customer_hist"], "city") == "varchar"


def test_ods_casts_keep_decimal_spacing_and_drop_ambiguous_columns():
    sql = (
        "    cast(total_amount as DECIMAL(18,  2)) as total_amount,\n"
        "    cast(a as bigint) as a,\n"
        "    cast(a as varchar) as a,\n"
        "    cast(raw_b as bigint) as b,\n"
    )

    assert ods_casts(sql) == {"total_amount": "decimal(18, 2)"}


def test_a_missing_project_has_no_types(tmp_path):
    assert load_column_types(tmp_path / "absent") == ColumnTypes()


def test_a_yml_that_is_not_a_mapping_names_the_file(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models/bad.yml").write_text("- a\n- b\n")

    with pytest.raises(ColumnTypeError, match="bad.yml"):
        load_column_types(tmp_path)


def test_nameless_models_and_columns_are_skipped(tmp_path):
    write_yml(
        tmp_path / "models/x.yml",
        {"models": [{"columns": []}, {"name": "m", "columns": [{"data_type": "bigint"}, {"name": "c"}]}]},
    )

    assert load_column_types(tmp_path).models == {}


# --- passed-through columns ---


def test_dwd_id_takes_the_ods_models_declared_type(wh, tmp_path):
    text = dwd_order(wh, load_column_types(ods_project(tmp_path, yml_type="varchar", sql_type="bigint")))

    assert column_type(text, "order_id") == "varchar"
    assert "order_id" not in guess_comment(text)


def test_dwd_id_takes_the_ods_sql_cast_when_the_yml_is_silent(wh, tmp_path):
    text = dwd_order(wh, load_column_types(ods_project(tmp_path, sql_type="varchar")))

    assert column_type(text, "order_id") == "varchar"
    assert column_type(text, "created_at") == "timestamp(6) with time zone"
    assert guess_comment(text) == ""


def test_the_raw_source_type_is_never_used(wh, tmp_path):
    """ODS re-casts its columns: a source declared integer says nothing about what the DWD reads (I-1)."""
    project = ods_project(tmp_path, source_type="integer")
    (project / "models/ods/shop/ods_shop_orders_di.sql").write_text("select * from x\n")

    with pytest.raises(ScaffoldError, match=r"ods_shop_orders_di neither declares .* nor casts"):
        dwd_order(wh, load_column_types(project))


def test_an_ods_upstream_that_cannot_type_a_column_is_refused(wh, tmp_path):
    with pytest.raises(ScaffoldError, match=r"order_id: ods_shop_orders_di .* declare `data_type`"):
        dwd_order(wh, load_column_types(ods_project(tmp_path)))


def test_an_unknown_upstream_keeps_the_name_guess_and_lists_it(wh, tmp_path):
    text = dwd_order(wh, load_column_types(tmp_path), upstream=["ods_shop_orders_di"])

    assert column_type(text, "order_id") == "bigint"
    assert "order_id" in guess_comment(text)
    assert guess_comment(text).startswith("#")
    yaml.safe_load(text)


def test_without_any_project_every_passed_through_column_is_flagged(wh):
    text = dwd_order(wh, None)

    comment = guess_comment(text)
    assert "order_id" in comment
    assert "created_at" in comment
    assert "order_date_key" not in comment
    assert " dt" not in comment


def test_dwd_event_at_keeps_a_declared_non_default_timestamp(wh, tmp_path):
    write_yml(
        tmp_path / "models/x.yml",
        {
            "models": [
                {
                    "name": "stg_orders",
                    "columns": [
                        {"name": "order_id", "data_type": "bigint"},
                        {"name": "created_at", "data_type": "timestamp(3) with time zone"},
                    ],
                }
            ]
        },
    )

    text = dwd_order(wh, load_column_types(tmp_path), upstream=["stg_orders"])

    assert column_type(text, "created_at") == "timestamp(3) with time zone"


def test_the_first_upstream_that_declares_a_column_wins(wh, tmp_path):
    write_yml(
        tmp_path / "models/x.yml",
        {
            "models": [
                {
                    "name": "a_model",
                    "columns": [{"name": "created_at", "data_type": "timestamp(3) with time zone"}],
                },
                {"name": "b_model", "columns": [{"name": "order_id", "data_type": "varchar"}]},
                {"name": "c_model", "columns": [{"name": "order_id", "data_type": "integer"}]},
            ]
        },
    )

    text = dwd_order(wh, load_column_types(tmp_path), upstream=["a_model", "b_model", "c_model"])

    assert column_type(text, "order_id") == "varchar"


def test_dimension_attributes_and_special_members_use_the_declared_type(make_warehouse, tmp_path):
    def segment_id(files):
        customer = files["dimensions"]["dimensions"][1]
        customer["attributes"].append({"name": "segment_id", "description": "Segment.", "history": "current"})

    wh = load_warehouse(make_warehouse(mutate=segment_id))
    write_yml(
        tmp_path / "models/ods/shop/_shop__models.yml",
        {
            "models": [
                {
                    "name": "ods_shop_customers_df",
                    "columns": [
                        {"name": "customer_id", "data_type": "varchar"},
                        {"name": "city", "data_type": "varchar"},
                        {"name": "segment_id", "data_type": "varchar"},
                        {"name": "updated_at", "data_type": "timestamp(6) with time zone"},
                    ],
                }
            ]
        },
    )

    files = scaffold(
        "dim_pub_customer",
        wh,
        project_dir="",
        upstream=["ods_shop_customers_df"],
        column_types=load_column_types(tmp_path),
    )

    text = files["models/dim/pub/dim_pub_customer.yml"]
    sql = files["models/dim/pub/dim_pub_customer.sql"]
    assert column_type(text, "customer_id") == "varchar"
    assert column_type(text, "segment_id") == "varchar"  # the name alone would guess bigint
    assert guess_comment(text) == ""
    assert re.search(r"cast\(null as varchar\)\s+as customer_id", sql)
    assert re.search(r"'Unknown'\s+as segment_id", sql)  # a declared-varchar attribute carries the label


def test_dws_grain_column_takes_the_declared_type(make_warehouse, tmp_path):
    wh = load_warehouse(make_warehouse())
    write_yml(
        tmp_path / "models/dwd/trade/_trade__models.yml",
        {
            "models": [
                {
                    "name": "dwd_trade_order_di",
                    "columns": [
                        {"name": "customer_key", "data_type": "varchar(32)"},
                        {"name": "order_amt", "data_type": "decimal(18, 2)"},
                    ],
                }
            ]
        },
    )

    files = scaffold(
        "dws_trade_customer_1d",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=["order_amt_sum_1d"],
        upstream=["dwd_trade_order_di"],
        column_types=load_column_types(tmp_path),
    )

    text = files["models/dws/trade/dws_trade_customer_1d.yml"]
    assert column_type(text, "customer_key") == "varchar(32)"
    assert guess_comment(text) == ""


def test_cli_reads_types_from_the_project_dir(make_warehouse, tmp_path, capsys):
    warehouse = make_warehouse()
    project = ods_project(tmp_path / "proj", sql_type="varchar")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        code = main(
            [
                "scaffold",
                "dwd_trade_order_di",
                "--from",
                "ods_shop_orders_di",
                "--grain",
                "order_id",
                "--event-at",
                "created_at",
                "--warehouse",
                str(warehouse),
                "--project-dir",
                str(project.relative_to(tmp_path)),
            ]
        )
    finally:
        os.chdir(cwd)

    assert code == 0
    out = capsys.readouterr().out
    yml = out.split("# proj/models/dwd/trade/dwd_trade_order_di.yml\n", 1)[1]
    assert column_type(yml, "order_id") == "varchar"


def test_the_real_project_types_payment_id_as_varchar():
    types = load_column_types(REPO / "dags/dbt")

    assert types.upstream_type(["ods_shop_payments_di"], "payment_id") == "varchar"
    assert types.upstream_type(["ods_shop_payments_di"], "paid_at") == "timestamp(6) with time zone"
    assert types.upstream_type(["ods_shop_payments_di"], "amount") == "decimal(18, 2)"


# --- stored metric types ---


def with_measure(name: str, aggregation: str):
    """A warehouse mutation adding atomic `name` and its 1d derived metric `<name>_<aggregation>_1d`."""

    def mutate(files):
        files["metrics"]["atomic"].append(
            {
                "name": name,
                "process": "order",
                "description": "A measure.",
                "aggregation": aggregation,
                "additivity": "additive" if aggregation == "sum" else "non_additive",
            }
        )
        files["metrics"]["derived"].append(
            {
                "name": f"{name}_{aggregation}_1d",
                "atomic": name,
                "period": "1d",
                "grain": ["customer"],
                "description": "Per customer per day.",
            }
        )

    return mutate


@pytest.mark.parametrize(
    ("measure", "aggregation", "declared", "expected"),
    [
        ("order_status", "max", None, "varchar"),
        ("order_status", "min", None, "varchar"),
        ("first_order_date", "min", None, "date"),
        ("paid_at", "max", None, "timestamp(6) with time zone"),
        ("order_qty", "max", "integer", "integer"),
        ("order_qty", "max", "INTEGER", "integer"),
        ("order_qty", "sum", "integer", "bigint"),
        ("order_qty", "sum", "INTEGER", "bigint"),
        ("order_qty", "sum", "smallint", "bigint"),
        ("order_qty", "sum", "tinyint", "bigint"),
        ("order_qty", "sum", "bigint", "bigint"),
        ("order_rate", "sum", "double", "double"),
        ("order_rate", "sum", "Real", "real"),
        ("order_amt", "sum", None, "decimal(38, 2)"),
        ("order_amt", "sum", "decimal(10, 0)", "decimal(38, 0)"),
        ("order_amt", "sum", "decimal(10)", "decimal(38, 0)"),
        ("order_amt", "sum", "DECIMAL(18,4)", "decimal(38, 4)"),
        ("order_amt", "max", "DECIMAL(18,4)", "decimal(18, 4)"),
        ("order_cnt", "sum", None, "bigint"),
    ],
)
def test_metric_type_is_explicit_for_every_aggregation(
    make_warehouse, measure, aggregation, declared, expected
):
    wh = load_warehouse(make_warehouse(mutate=with_measure(measure, aggregation)))

    assert metric_type(wh, f"{measure}_{aggregation}_1d", declared) == expected


def test_sum_of_a_guessed_non_numeric_measure_says_to_declare_it(make_warehouse):
    wh = load_warehouse(make_warehouse(mutate=with_measure("order_status", "sum")))

    with pytest.raises(
        ScaffoldError, match=r"no upstream model declares order_status.*declare its data_type"
    ):
        metric_type(wh, "order_status_sum_1d")


@pytest.mark.parametrize("declared", ["varchar", "date", "boolean"])
def test_sum_of_a_declared_non_numeric_measure_names_the_declared_type(make_warehouse, declared):
    wh = load_warehouse(make_warehouse(mutate=with_measure("order_amt", "sum")))

    with pytest.raises(ScaffoldError, match=rf"declared type {declared} is not numeric"):
        metric_type(wh, "order_amt_sum_1d", declared)


def dws_files(wh, metric, types=None):
    return scaffold(
        "dws_trade_customer_1d",
        wh,
        project_dir="",
        grain=["customer_key"],
        metrics=[metric],
        upstream=["dwd_trade_order_di"],
        column_types=types,
    )["models/dws/trade/dws_trade_customer_1d.yml"]


def test_dws_metric_type_uses_the_upstream_declared_measure_type(make_warehouse, tmp_path):
    wh = load_warehouse(make_warehouse(mutate=with_measure("order_qty", "sum")))
    write_yml(
        tmp_path / "models/dwd/trade/_trade__models.yml",
        {
            "models": [
                {"name": "dwd_trade_order_di", "columns": [{"name": "order_qty", "data_type": "integer"}]}
            ]
        },
    )

    text = dws_files(wh, "order_qty_sum_1d", load_column_types(tmp_path))

    assert column_type(text, "order_qty_sum_1d") == "bigint"
    assert "order_qty" not in guess_comment(text)


def test_a_metric_typed_from_a_guessed_measure_is_listed(make_warehouse):
    """max(order_qty) with nothing declared is typed from the name guess; the .yml must say so (I-2)."""
    wh = load_warehouse(make_warehouse(mutate=with_measure("order_qty", "max")))

    text = dws_files(wh, "order_qty_max_1d")

    assert "measure type guessed" in guess_comment(text)
    assert "order_qty" in guess_comment(text)


def test_a_count_metric_lists_no_measure(make_warehouse):
    wh = load_warehouse(make_warehouse())

    assert "measure type guessed" not in guess_comment(dws_files(wh, "order_cnt_1d"))


def test_dws_refuses_a_sum_it_cannot_type(make_warehouse):
    wh = load_warehouse(make_warehouse(mutate=with_measure("order_status", "sum")))

    with pytest.raises(ScaffoldError, match="declare its data_type"):
        dws_files(wh, "order_status_sum_1d")
