"""iceberg_maintenance deletes dt partitions older than the retention and keeps newer ones."""

import shutil

import pytest
import yaml
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest_maint"
ODS = f'{CATALOG}."{SCHEMA}_ods".ods_shop_orders_di'


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


def columns() -> str:
    rows = query(
        f"SELECT column_name FROM {CATALOG}.information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}_ods' AND table_name = 'ods_shop_orders_di' AND column_name <> 'dt' "
        "ORDER BY ordinal_position"
    )
    return ", ".join(r[0] for r in rows)


def test_old_partitions_are_deleted_and_recent_ones_kept():
    run_dbt(MAIN_PROJECT, ["build", "--select", "ods_shop_orders_di", "--vars", "{dt: '2026-11-02'}"], SCHEMA)
    cols = columns()
    query(
        f"INSERT INTO {ODS} ({cols}, dt) "
        f"SELECT {cols}, DATE '2024-01-01' FROM {ODS} WHERE dt = DATE '2026-11-02'"
    )

    dry_run = run_dbt(
        MAIN_PROJECT,
        [
            "run-operation",
            "iceberg_maintenance",
            "--args",
            "{dry_run: true}",
            "--vars",
            "{maintenance_today: '2026-11-04'}",
        ],
        SCHEMA,
    )
    # The dry run logs every statement, with the ODS layer default of 400 days, and runs none.
    assert "[dry run] delete from" in dry_run
    assert "ods_shop_orders_di\" where dt < date_add('day', -400, date '2026-11-04')" in dry_run
    assert "execute optimize" in dry_run
    assert "execute expire_snapshots(retention_threshold => '7d')" in dry_run
    assert "execute remove_orphan_files(retention_threshold => '7d')" in dry_run
    assert query(f"SELECT count(DISTINCT dt) FROM {ODS}") == [(2,)]

    run_dbt(
        MAIN_PROJECT,
        [
            "run-operation",
            "iceberg_maintenance",
            "--args",
            "{dry_run: false}",
            "--vars",
            "{maintenance_today: '2026-11-04'}",
        ],
        SCHEMA,
    )
    assert query(f"SELECT DISTINCT dt FROM {ODS}")[0][0].isoformat() == "2026-11-02"


def test_model_retention_days_overrides_the_layer_default(tmp_path):
    # A copy of the project whose ods_shop_orders_di says retention_days: 30, so no tracked file changes.
    project = tmp_path / "dbt_retention"
    shutil.copytree(MAIN_PROJECT, project, ignore=shutil.ignore_patterns("dbt_packages", "target", "logs"))
    models_yml = project / "models" / "ods" / "shop" / "_shop__models.yml"
    document = yaml.safe_load(models_yml.read_text())
    for model in document["models"]:
        if model["name"] == "ods_shop_orders_di":
            model.setdefault("config", {}).setdefault("meta", {})["retention_days"] = 30
    models_yml.write_text(yaml.safe_dump(document, sort_keys=False))

    before = query(f"SELECT count(*) FROM {ODS}")
    output = run_dbt(
        project,
        ["run-operation", "iceberg_maintenance", "--vars", "{maintenance_today: '2026-11-04'}"],
        SCHEMA,
    )

    # dry_run defaults to true: the statement is logged with the override, and the table is untouched.
    assert "ods_shop_orders_di\" where dt < date_add('day', -30, date '2026-11-04')" in output
    assert query(f"SELECT count(*) FROM {ODS}") == before
