"""`dwh scaffold` takes a passed-through column's type from upstream declarations (M-2)."""

import os
import re
from pathlib import Path

import pytest
import yaml

from dwh.cli import main
from dwh.column_types import ColumnTypes, load_column_types
from dwh.scaffold import scaffold
from dwh.warehouse import load_warehouse

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def wh(make_warehouse):
    return load_warehouse(make_warehouse())


def write_yml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def ods_project(root: Path, *, order_id_type=None, source_meta_type=None) -> Path:
    """A dbt project with ods_shop_orders_di and its source; types declared only where asked."""
    order_id: dict = {"name": "order_id", "description": "Order id."}
    if order_id_type:
        order_id["data_type"] = order_id_type
    write_yml(
        root / "models/ods/shop/_shop__models.yml",
        {"version": 2, "models": [{"name": "ods_shop_orders_di", "columns": [order_id]}]},
    )
    source_column: dict = {"name": "order_id"}
    if source_meta_type:
        source_column["config"] = {"meta": {"data_type": source_meta_type}}
    write_yml(
        root / "models/ods/shop/_shop__sources.yml",
        {
            "version": 2,
            "sources": [{"name": "shop", "tables": [{"name": "orders", "columns": [source_column]}]}],
        },
    )
    return root


def dwd_order(wh, types):
    return scaffold(
        "dwd_trade_order_di",
        wh,
        project_dir="",
        grain=["order_id"],
        upstream=["ods_shop_orders_di"],
        event_at="created_at",
        column_types=types,
    )["models/dwd/trade/dwd_trade_order_di.yml"]


def column_type(text: str, name: str) -> str:
    model = yaml.safe_load(text)["models"][0]
    return {c["name"]: c for c in model["columns"]}[name]["data_type"]


def guess_comment(text: str) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if "guessed from the column name" in line)


def test_load_column_types_reads_model_and_source_declarations(tmp_path):
    project = ods_project(tmp_path, order_id_type="varchar", source_meta_type="integer")

    types = load_column_types(project)

    assert types.models["ods_shop_orders_di"]["order_id"] == "varchar"
    assert types.sources[("shop", "orders")]["order_id"] == "integer"


def test_load_column_types_reads_a_source_columns_own_data_type(tmp_path):
    write_yml(
        tmp_path / "models/ods/shop/_shop__sources.yml",
        {
            "version": 2,
            "sources": [
                {
                    "name": "shop",
                    "tables": [
                        {"name": "payments", "columns": [{"name": "payment_id", "data_type": "varchar"}]}
                    ],
                }
            ],
        },
    )

    assert load_column_types(tmp_path).sources[("shop", "payments")]["payment_id"] == "varchar"


def test_a_missing_project_has_no_declared_types(tmp_path):
    types = load_column_types(tmp_path / "absent")
    assert types == ColumnTypes({}, {})


def test_dwd_id_takes_the_upstream_models_declared_type(wh, tmp_path):
    types = load_column_types(ods_project(tmp_path, order_id_type="varchar"))

    text = dwd_order(wh, types)

    assert column_type(text, "order_id") == "varchar"
    assert "order_id" not in guess_comment(text)


def test_dwd_id_falls_back_to_the_ods_sources_column_meta(wh, tmp_path):
    types = load_column_types(ods_project(tmp_path, source_meta_type="varchar"))

    assert column_type(dwd_order(wh, types), "order_id") == "varchar"


def test_the_upstream_model_declaration_wins_over_the_source(wh, tmp_path):
    types = load_column_types(ods_project(tmp_path, order_id_type="bigint", source_meta_type="varchar"))

    assert column_type(dwd_order(wh, types), "order_id") == "bigint"


def test_an_unknown_id_type_keeps_bigint_and_says_it_is_a_guess(wh, tmp_path):
    types = load_column_types(ods_project(tmp_path))

    text = dwd_order(wh, types)

    assert column_type(text, "order_id") == "bigint"
    comment = guess_comment(text)
    assert comment.startswith("#")
    assert "order_id" in comment
    yaml.safe_load(text)  # the comment keeps the file valid YAML


def test_without_any_declarations_every_passed_through_column_is_flagged(wh):
    text = dwd_order(wh, None)

    assert column_type(text, "order_id") == "bigint"
    comment = guess_comment(text)
    assert "order_id" in comment
    assert "created_at" in comment
    # Keys and dt are computed by the scaffold, not passed through, so they are never guesses.
    assert "order_date_key" not in comment
    assert " dt" not in comment


def test_dimension_natural_key_and_special_members_use_the_declared_type(wh, tmp_path):
    write_yml(
        tmp_path / "models/ods/shop/_shop__models.yml",
        {
            "version": 2,
            "models": [
                {
                    "name": "ods_shop_customers_df",
                    "columns": [
                        {"name": "customer_id", "data_type": "varchar"},
                        {"name": "city", "data_type": "varchar"},
                        {"name": "updated_at", "data_type": "timestamp(6) with time zone"},
                    ],
                }
            ],
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
    assert column_type(text, "customer_id") == "varchar"
    assert guess_comment(text) == ""
    sql = files["models/dim/pub/dim_pub_customer.sql"]
    assert re.search(r"cast\(null as varchar\)\s+as customer_id", sql)


def test_cli_reads_types_from_the_project_dir(make_warehouse, tmp_path, capsys):
    warehouse = make_warehouse()
    project = ods_project(tmp_path / "proj", order_id_type="varchar")
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


def test_the_real_project_declares_payment_id_as_varchar():
    types = load_column_types(REPO / "dags/dbt")

    assert types.upstream_type(["ods_shop_payments_di"], "payment_id") == "varchar"
    assert types.upstream_type(["ods_shop_payments_di"], "order_id") == "bigint"
