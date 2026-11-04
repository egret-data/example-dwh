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


def test_rerun_with_empty_batch_clears_the_dt_partition():
    # The source stops yielding rows for 2026-11-02 (rows deleted), then the dt is re-run.
    # The shared `shop` fixture is restored in `finally`.
    columns = "order_id, customer_id, order_status, total_amount, created_at, updated_at"
    rows = query(
        f"SELECT {columns} FROM shop.public.orders "
        "WHERE updated_at >= TIMESTAMP '2026-11-02 00:00:00' AND updated_at < TIMESTAMP '2026-11-03 00:00:00'"
    )
    assert len(rows) == 2
    ids = ", ".join(str(row[0]) for row in rows)
    query(f"DELETE FROM shop.public.orders WHERE order_id IN ({ids})")
    try:
        build("2026-11-02")

        assert count("ods_shop_orders_di", "2026-11-02") == 0
        assert count("ods_shop_orders_di", "2026-11-03") == 3
    finally:
        values = ", ".join(
            f"({oid}, {cid}, '{status}', DECIMAL '{amount}', TIMESTAMP '{created}', TIMESTAMP '{updated}')"
            for oid, cid, status, amount, created, updated in rows
        )
        query(f"INSERT INTO shop.public.orders ({columns}) VALUES {values}")
