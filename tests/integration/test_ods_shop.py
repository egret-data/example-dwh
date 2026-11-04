"""ODS load for source `shop`: partition replacement by dt, idempotent re-runs.

Tests run in file order and share state: each builds on the previous load.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest"
ODS = f'{CATALOG}."{SCHEMA}_ods"'


def build(dt: str) -> str:
    return run_dbt(MAIN_PROJECT, ["build", "--select", "tag:ods_shop", "--vars", f"{{dt: '{dt}'}}"], SCHEMA)


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


def test_vietnam_day_unit_tests_run_in_the_ods_build():
    out = build("2026-11-02")

    assert "orders_di_window_is_the_vietnam_day" in out
    assert "orders_di_converts_a_utc_source_to_the_vietnam_day" in out


def test_timestamps_are_stored_with_time_zone():
    rows = query(
        f"SELECT column_name, data_type FROM {CATALOG}.information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}_ods' AND table_name = 'ods_shop_orders_di' "
        "AND column_name IN ('created_at', 'updated_at') ORDER BY column_name"
    )

    assert rows == [
        ("created_at", "timestamp(6) with time zone"),
        ("updated_at", "timestamp(6) with time zone"),
    ]


def test_next_dt_adds_partition_and_keeps_previous():
    build("2026-11-03")
    assert count("ods_shop_orders_di", "2026-11-03") == 3
    assert count("ods_shop_orders_di", "2026-11-02") == 2
    dts = query(f"SELECT DISTINCT dt FROM {ODS}.ods_shop_customers_df ORDER BY dt")
    assert dts == [(date(2026, 11, 2),), (date(2026, 11, 3),)]


def test_shops_and_payments_load():
    build("2026-11-02")

    assert count("ods_shop_shops_df", "2026-11-02") == 2
    assert count("ods_shop_payments_di", "2026-11-02") == 2  # p4 (08:00) and p2 (14:05)
    assert query(f"SELECT sum(amount) FROM {ODS}.ods_shop_payments_di WHERE dt = DATE '2026-11-02'") == [
        (Decimal("330000.00"),)
    ]


def test_orders_carry_shop_and_channel():
    rows = query(
        f"SELECT order_id, shop_id, channel FROM {ODS}.ods_shop_orders_di WHERE dt = DATE '2026-11-02' ORDER BY 1"
    )
    assert rows == [(2, 1, "web"), (3, 2, "app")]


def test_rerun_with_empty_batch_clears_the_dt_partition():
    # The source stops yielding rows for 2026-11-02 (rows deleted), then the dt is re-run.
    # Payments reference their orders, so they are deleted first.
    # The shared `shop` fixture is restored in `finally`.
    columns = "order_id, customer_id, shop_id, channel, order_status, total_amount, created_at, updated_at"
    pay_columns = "payment_id, order_id, customer_id, shop_id, amount, method, paid_at, updated_at"
    rows = query(
        f"SELECT {columns} FROM shop.public.orders "
        "WHERE updated_at >= TIMESTAMP '2026-11-02 00:00:00' AND updated_at < TIMESTAMP '2026-11-03 00:00:00'"
    )
    assert len(rows) == 2
    ids = ", ".join(str(row[0]) for row in rows)
    payments = query(f"SELECT {pay_columns} FROM shop.public.payments WHERE order_id IN ({ids})")
    query(f"DELETE FROM shop.public.payments WHERE order_id IN ({ids})")
    query(f"DELETE FROM shop.public.orders WHERE order_id IN ({ids})")
    try:
        build("2026-11-02")

        assert count("ods_shop_orders_di", "2026-11-02") == 0
        assert count("ods_shop_orders_di", "2026-11-03") == 3
    finally:
        values = ", ".join(
            f"({oid}, {cid}, {sid}, '{channel}', '{status}', DECIMAL '{amount}', "
            f"TIMESTAMP '{created}', TIMESTAMP '{updated}')"
            for oid, cid, sid, channel, status, amount, created, updated in rows
        )
        query(f"INSERT INTO shop.public.orders ({columns}) VALUES {values}")
        pay_values = ", ".join(
            f"('{pid}', {oid}, {cid}, {sid}, DECIMAL '{amount}', '{method}', "
            f"TIMESTAMP '{paid}', TIMESTAMP '{updated}')"
            for pid, oid, cid, sid, amount, method, paid, updated in payments
        )
        query(f"INSERT INTO shop.public.payments ({pay_columns}) VALUES {pay_values}")


def test_orders_window_is_pushed_down_to_the_source():
    """The source column is compared raw, so Trino sends the dt window to the shop database."""
    run_dbt(
        MAIN_PROJECT, ["compile", "--select", "ods_shop_orders_di", "--vars", "{dt: '2026-11-02'}"], SCHEMA
    )
    compiled = Path(f"/tmp/dbt/target-{MAIN_PROJECT.name}/compiled/example_dwh/models/ods/shop")
    sql = (compiled / "ods_shop_orders_di.sql").read_text()

    plan = "\n".join(row[0] for row in query(f"EXPLAIN {sql}"))

    assert "constraint on [updated_at]" in plan, plan
