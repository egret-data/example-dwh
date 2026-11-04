"""ODS load for source `shop`: partition replacement by dt, idempotent re-runs.

Tests run in file order and share state: each builds on the previous load.
"""

from datetime import date

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest"
ODS = f'{CATALOG}."{SCHEMA}_ods"'


def build(dt: str) -> None:
    run_dbt(MAIN_PROJECT, ["build", "--select", "tag:ods_shop", "--vars", f"{{dt: '{dt}'}}"], SCHEMA)


def count(table: str, dt: str | None = None) -> int:
    where = f" WHERE dt = DATE '{dt}'" if dt else ""
    return query(f"SELECT count(*) FROM {ODS}.{table}{where}")[0][0]


@pytest.fixture(scope="module", autouse=True)
def clean():
    drop_schemas(SCHEMA)
    yield
    drop_schemas(SCHEMA)


def test_di_loads_only_rows_updated_on_dt():
    build("2026-11-02")
    assert count("ods_shop_orders_di", "2026-11-02") == 2
    assert count("ods_shop_orders_di") == 2


def test_df_loads_full_copy_into_dt():
    assert count("ods_shop_customers_df", "2026-11-02") == 3


def test_rerun_same_dt_is_idempotent():
    build("2026-11-02")
    assert count("ods_shop_orders_di") == 2
    assert count("ods_shop_customers_df") == 3


def test_next_dt_adds_partition_and_keeps_previous():
    build("2026-11-03")
    assert count("ods_shop_orders_di", "2026-11-03") == 3
    assert count("ods_shop_orders_di", "2026-11-02") == 2
    dts = query(f"SELECT DISTINCT dt FROM {ODS}.ods_shop_customers_df ORDER BY dt")
    assert dts == [(date(2026, 11, 2),), (date(2026, 11, 3),)]
