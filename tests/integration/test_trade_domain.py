"""The trade reference domain, run day by day as the DAGs would (plan 4). Tests share state, in file order."""

from datetime import UTC, date, datetime

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest_trade"
DAYS = ["2026-11-01", "2026-11-02", "2026-11-03"]
DOWNSTREAM = ("tag:domain:trade", "tag:app:crm")


def build(dt: str, *selectors: str) -> str:
    return run_dbt(MAIN_PROJECT, ["build", "--select", *selectors, "--vars", f"{{dt: '{dt}'}}"], SCHEMA)


def run_day(dt: str) -> None:
    build(dt, "tag:ods_shop")
    build(dt, "tag:domain:pub")
    build(dt, *DOWNSTREAM)


def table(layer: str, name: str) -> str:
    return f'{CATALOG}."{SCHEMA}_{layer}".{name}'


@pytest.fixture(scope="module", autouse=True)
def pipeline():
    drop_schemas(SCHEMA)
    try:
        run_day(DAYS[0])
        # Customer 102 moves on 2026-11-02 10:00 (Vietnam time): the SCD4 history must record it.
        query(
            "UPDATE shop.public.customers SET city = 'Ho Chi Minh', "
            "updated_at = TIMESTAMP '2026-11-02 10:00:00' WHERE customer_id = 102"
        )
        run_day(DAYS[1])
        run_day(DAYS[2])
        yield
    finally:
        query(
            "UPDATE shop.public.customers SET city = 'Da Nang', "
            "updated_at = TIMESTAMP '2026-10-05 09:00:00' WHERE customer_id = 102"
        )
        drop_schemas(SCHEMA)


def test_date_dimension_covers_the_calendar_and_special_members():
    rows = query(
        f"SELECT count(*), min(cal_date), max(cal_date) FROM {table('dim', 'dim_pub_date')} "
        "WHERE date_key NOT IN ('-1', '-2')"
    )
    assert rows == [(4018, date(2020, 1, 1), date(2030, 12, 31))]
    assert query(
        f"SELECT date_key FROM {table('dim', 'dim_pub_date')} WHERE cal_date IS NULL ORDER BY 1"
    ) == [("-1",), ("-2",)]


def test_customer_dimension_has_current_rows_and_labelled_special_members():
    rows = query(
        "SELECT customer_key, customer_id, customer_name, city "
        f"FROM {table('dim', 'dim_pub_customer')} ORDER BY customer_id NULLS FIRST, customer_key"
    )
    assert [r[1:] for r in rows if r[1] is not None] == [
        (101, "An", "Hanoi"),
        (102, "Binh", "Ho Chi Minh"),
        (103, "Chi", "Da Nang"),
    ]
    assert sorted((r[0], r[2], r[3]) for r in rows if r[1] is None) == [
        ("-1", "Unknown", "Unknown"),
        ("-2", "Not applicable", "Not applicable"),
    ]


def test_customer_history_records_the_move_at_the_source_change_time():
    rows = query(
        f"SELECT h.city, h.valid_from, h.valid_to FROM {table('dim', 'dim_pub_customer_hist')} h "
        f"JOIN {table('dim', 'dim_pub_customer')} d ON d.customer_key = h.customer_key "
        "WHERE d.customer_id = 102 ORDER BY h.valid_from"
    )
    utc = UTC
    assert [
        (r[0], r[1].astimezone(utc).replace(tzinfo=None), r[2] and r[2].astimezone(utc).replace(tzinfo=None))
        for r in rows
    ] == [
        ("Da Nang", datetime(2026, 10, 5, 2, 0), datetime(2026, 11, 2, 3, 0)),
        ("Ho Chi Minh", datetime(2026, 11, 2, 3, 0), None),
    ]


def test_shop_dimension():
    rows = query(
        f"SELECT shop_id, shop_name, city FROM {table('dim', 'dim_trade_shop')} "
        "WHERE shop_id IS NOT NULL ORDER BY 1"
    )
    assert rows == [(1, "An Shop", "Hanoi"), (2, "Binh Shop", "Ho Chi Minh")]
