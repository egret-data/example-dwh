"""The trade reference domain, run day by day as the DAGs would (plan 4). Tests share state, in file order."""

from datetime import UTC, date, datetime

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest_trade"
DAYS = ["2026-11-01", "2026-11-02", "2026-11-03"]
DOWNSTREAM = ("tag:domain:trade", "tag:app:crm")


def build(dt: str, *selectors: str) -> str:
    # buildable: a test runs only when every model it touches is selected or upstream of the selection, so the
    # pub build does not pick up the DWD relationships tests whose tables the later trade build creates.
    args = ["build", "--indirect-selection", "buildable", "--select", *selectors, "--vars", f"{{dt: '{dt}'}}"]
    return run_dbt(MAIN_PROJECT, args, SCHEMA)


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


def order_ids_by_dt() -> dict:
    rows = query(f"SELECT dt, order_id FROM {table('dwd', 'dwd_trade_order_di')} ORDER BY dt, order_id")
    result: dict = {}
    for dt, order_id in rows:
        result.setdefault(dt.isoformat(), []).append(order_id)
    return result


def test_sequential_run_misses_orders_first_loaded_after_their_event_day():
    # Orders 2 and 4 first appear in the ODS partition after the day they were placed (STD-05-08).
    assert order_ids_by_dt() == {"2026-11-01": [1], "2026-11-02": [3], "2026-11-03": [5, 6]}


def test_backfill_oldest_first_picks_up_late_rows():
    for dt in DAYS:  # dwh-backfill: oldest dt first, through today, downstream models included
        build(dt, *DOWNSTREAM)
    assert order_ids_by_dt() == {"2026-11-01": [1, 2], "2026-11-02": [3, 4], "2026-11-03": [5, 6]}


def test_orders_carry_the_city_the_customer_had_when_ordering():
    rows = query(
        f"SELECT order_id, customer_city FROM {table('dwd', 'dwd_trade_order_di')} "
        "WHERE order_id IN (2, 5) ORDER BY 1"
    )
    assert rows == [(2, "Da Nang"), (5, "Ho Chi Minh")]


def test_payments_are_event_facts_on_the_pay_day():
    rows = query(
        f"SELECT dt, count(*), sum(pay_amt) FROM {table('dwd', 'dwd_trade_payment_di')} "
        "GROUP BY dt ORDER BY dt"
    )
    assert [(r[0].isoformat(), r[1], int(r[2])) for r in rows] == [
        ("2026-11-01", 1, 120000),
        ("2026-11-02", 2, 330000),
        ("2026-11-03", 1, 99000),
    ]


def test_lifecycle_has_one_row_per_order_and_marks_unpaid_orders():
    rows = query(
        f"SELECT order_id, is_paid, pay_date_key FROM {table('dwd', 'dwd_trade_order_lifecycle_di')} "
        "ORDER BY 1"
    )
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert {r[0] for r in rows if r[1]} == {1, 2, 3, 5}
    assert [r[2] for r in rows if not r[1]] == ["-2", "-2"]


def test_lifecycle_order_paid_on_a_later_day_keeps_its_placed_day_and_payment():
    rows = query(
        "SELECT dt, pay_amt, pay_date_key FROM "
        f"{table('dwd', 'dwd_trade_order_lifecycle_di')} WHERE order_id = 2"
    )
    assert [(r[0].isoformat(), int(r[1]), r[2] != "-2") for r in rows] == [("2026-11-01", 80000, True)]


def test_rerunning_an_old_day_alone_does_not_regress_later_payments():
    build("2026-11-01", *DOWNSTREAM)
    rows = query(
        f"SELECT is_paid, pay_amt, dt FROM {table('dwd', 'dwd_trade_order_lifecycle_di')} WHERE order_id = 2"
    )
    assert [(r[0], int(r[1]), r[2].isoformat()) for r in rows] == [(True, 80000, "2026-11-01")]
