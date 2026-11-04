import pytest

from dwh.cli import main
from fixtures.manifest import good_project


def test_good_project_is_clean_for_every_family(lint):
    builder, _ = good_project()
    assert lint(builder) == []


def test_cli_lint_clean_exits_0(make_warehouse, write_manifest, capsys):
    builder, _ = good_project()

    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(write_manifest(builder))])

    assert rc == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"


def test_cli_lint_reports_findings_and_exits_1(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""

    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(write_manifest(builder))])

    out = capsys.readouterr().out
    assert rc == 1
    assert (
        "models/dwd/trade/dwd_trade_order_di.sql: DWH-D01 dwd_trade_order_di: model has no description" in out
    )


def test_cli_lint_select_filters_by_code_prefix(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""

    rc = main(
        [
            "lint",
            "--warehouse",
            str(make_warehouse()),
            "--manifest",
            str(write_manifest(builder)),
            "--select",
            "DWH-T",
        ]
    )

    assert rc == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"


def test_cli_lint_runs_yaml_validation_first(make_warehouse, write_manifest, capsys):
    builder, _ = good_project()

    rc = main(
        [
            "lint",
            "--warehouse",
            str(make_warehouse(drop=["glossary"])),
            "--manifest",
            str(write_manifest(builder)),
        ]
    )

    assert rc == 1
    assert "DWH-Y01" in capsys.readouterr().out


def test_cli_lint_missing_manifest_exits_2(make_warehouse, tmp_path, capsys):
    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(tmp_path / "nope.json")])

    assert rc == 2
    assert "make manifest" in capsys.readouterr().err


def test_cli_lint_select_never_hides_yaml_findings(make_warehouse, write_manifest, capsys):
    builder, _ = good_project()

    rc = main(
        [
            "lint",
            "--warehouse",
            str(make_warehouse(drop=["glossary"])),
            "--manifest",
            str(write_manifest(builder)),
            "--select",
            "DWH-T",
        ]
    )

    assert rc == 1
    assert "DWH-Y01" in capsys.readouterr().out


@pytest.mark.parametrize("content", ["{}", "not json", "[]"])
def test_cli_lint_unreadable_manifest_exits_2(make_warehouse, tmp_path, capsys, content):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(content)

    rc = main(["lint", "--warehouse", str(make_warehouse()), "--manifest", str(manifest)])

    assert rc == 2
    assert "not a readable dbt manifest" in capsys.readouterr().err


def test_cli_lint_prefixes_paths_with_project_dir(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""

    rc = main(
        [
            "lint",
            "--warehouse",
            str(make_warehouse()),
            "--manifest",
            str(write_manifest(builder)),
            "--project-dir",
            "dags/dbt",
        ]
    )

    assert rc == 1
    assert "dags/dbt/models/dwd/trade/dwd_trade_order_di.sql: DWH-D01" in capsys.readouterr().out


def test_cli_lint_changed_keeps_findings_in_changed_folders(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""
    builder.node(ids["ads_customer"])["description"] = ""

    rc = main(
        [
            "lint",
            "--warehouse",
            str(make_warehouse()),
            "--manifest",
            str(write_manifest(builder)),
            "--project-dir",
            "dags/dbt",
            "--changed",
            "dags/dbt/models/dwd/trade/_trade__models.yml",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 1
    assert "dwd_trade_order_di: model has no description" in out
    assert "ads_bi_customer_daily" not in out


def test_cli_lint_changed_without_files_reports_nothing(make_warehouse, write_manifest, capsys):
    builder, ids = good_project()
    builder.node(ids["dwd_order"])["description"] = ""

    rc = main(
        [
            "lint",
            "--warehouse",
            str(make_warehouse()),
            "--manifest",
            str(write_manifest(builder)),
            "--changed",
        ]
    )

    assert rc == 0
    assert capsys.readouterr().out.strip() == "0 finding(s)"
