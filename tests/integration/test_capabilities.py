"""Prove dbt-trino features the standards rely on: incremental merge and check-strategy snapshots."""

from datetime import date
from pathlib import Path

import pytest
from conftest import CATALOG, drop_schemas, query, run_dbt

PROJECT = Path(__file__).resolve().parent / "dbt_capabilities"
SCHEMA = "itest_cap"


def dbt(args: list[str], batch: int) -> None:
    run_dbt(PROJECT, [*args, "--vars", f"{{batch: {batch}}}"], SCHEMA)


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


def test_merge_updates_matched_rows_inserts_new_and_moves_partition():
    dbt(["run", "--select", "chk_merge"], batch=1)
    dbt(["run", "--select", "chk_merge"], batch=2)

    rows = query(f'SELECT id, v, dt FROM {CATALOG}."{SCHEMA}".chk_merge ORDER BY id')

    assert rows == [
        (1, "a", date(2026, 11, 1)),
        (2, "b2", date(2026, 11, 2)),
        (3, "c", date(2026, 11, 2)),
    ]


def test_check_snapshot_closes_changed_row_and_opens_new_version():
    dbt(["run", "--select", "chk_scd2_src"], batch=1)
    dbt(["snapshot"], batch=1)
    dbt(["run", "--select", "chk_scd2_src"], batch=2)
    dbt(["snapshot"], batch=2)

    rows = query(
        f"SELECT id, v, dbt_valid_to IS NULL AS is_current "
        f'FROM {CATALOG}."{SCHEMA}".chk_scd2 ORDER BY id, dbt_valid_from'
    )

    assert rows == [(1, "a", False), (1, "a2", True), (2, "b", True)]
