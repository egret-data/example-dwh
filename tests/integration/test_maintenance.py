"""iceberg_maintenance deletes dt partitions older than the retention and keeps newer ones."""

import pytest
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

    run_dbt(
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
