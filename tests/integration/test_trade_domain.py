"""The trade reference domain, run day by day as the DAGs would (plan 4). Tests share state, in file order."""

from datetime import UTC, date, datetime

import pytest
from helpers import CATALOG, MAIN_PROJECT, drop_schemas, query, run_dbt

SCHEMA = "itest_trade"
DAYS = ["2026-11-01", "2026-11-02", "2026-11-03"]
DOWNSTREAM = ("tag:domain:trade", "tag:app:crm")


TRADE_BUILD_OUTPUT: list[str] = []


def build(dt: str, *selectors: str) -> str:
    # buildable: a test runs only when every model it touches is selected or upstream of the selection, so the
    # pub build does not pick up the DWD relationships tests whose tables the later trade build creates.
    args = ["build", "--indirect-selection", "buildable", "--select", *selectors, "--vars", f"{{dt: '{dt}'}}"]
    output = run_dbt(MAIN_PROJECT, args, SCHEMA)
    if selectors == DOWNSTREAM:
        TRADE_BUILD_OUTPUT.append(output)
    return output


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


def dws(name: str, columns: str, dt: str) -> list:
    return query(
        f"SELECT d.customer_id, {columns} FROM {table('dws', name)} s "
        f"JOIN {table('dim', 'dim_pub_customer')} d ON d.customer_key = s.customer_key "
        f"WHERE s.dt = DATE '{dt}' ORDER BY d.customer_id"
    )


def ints(rows):
    return [tuple(None if v is None else int(v) for v in r) for r in rows]


def test_dws_1d():
    cols = "order_amt_sum_1d, order_cnt_1d, app_order_amt_sum_1d"
    assert ints(dws("dws_trade_customer_1d", cols, "2026-11-01")) == [
        (101, 120000, 1, 120000),
        (102, 80000, 1, None),
    ]
    assert ints(dws("dws_trade_customer_1d", cols, "2026-11-02")) == [
        (101, 40000, 1, None),
        (103, 250000, 1, 250000),
    ]
    assert ints(dws("dws_trade_customer_1d", cols, "2026-11-03")) == [
        (102, 99000, 1, 99000),
        (103, 15000, 1, 15000),
    ]


def test_dws_nd_and_td_on_the_last_day():
    assert ints(dws("dws_trade_customer_nd", "order_amt_sum_30d", "2026-11-03")) == [
        (101, 160000),
        (102, 179000),
        (103, 265000),
    ]
    assert ints(dws("dws_trade_customer_td", "order_amt_sum_td, order_cnt_td", "2026-11-03")) == [
        (101, 160000, 2),
        (102, 179000, 2),
        (103, 265000, 2),
    ]


def test_ads_customer_value():
    rows = query(
        f"SELECT d.customer_id, a.avg_order_amt_td FROM {table('ads', 'ads_crm_customer_value')} a "
        f"JOIN {table('dim', 'dim_pub_customer')} d ON d.customer_key = a.customer_key "
        "WHERE a.dt = DATE '2026-11-03' ORDER BY 1"
    )
    assert [(r[0], float(r[1])) for r in rows] == [(101, 80000.0), (102, 89500.0), (103, 132500.0)]


def test_reconciliation_dwd_to_dws_and_payments_to_source():
    dwd = query(
        f"SELECT dt, sum(order_amt) FROM {table('dwd', 'dwd_trade_order_di')} GROUP BY dt ORDER BY dt"
    )
    dws_1d = query(
        f"SELECT dt, sum(order_amt_sum_1d) FROM {table('dws', 'dws_trade_customer_1d')} "
        "GROUP BY dt ORDER BY dt"
    )
    assert [(r[0], int(r[1])) for r in dwd] == [(r[0], int(r[1])) for r in dws_1d]
    assert [int(r[1]) for r in dwd] == [200000, 290000, 114000]
    paid = query(f"SELECT sum(pay_amt) FROM {table('dwd', 'dwd_trade_payment_di')}")[0][0]
    source = query("SELECT sum(amount) FROM shop.public.payments")[0][0]
    assert int(paid) == int(source) == 549000


def test_rerunning_the_last_day_is_idempotent():
    before = query(f"SELECT count(*), sum(order_amt_sum_td) FROM {table('dws', 'dws_trade_customer_td')}")
    run_day(DAYS[2])
    assert (
        query(f"SELECT count(*), sum(order_amt_sum_td) FROM {table('dws', 'dws_trade_customer_td')}")
        == before
    )


def test_buildable_selection_still_runs_the_date_key_relationships_tests():
    # dim_pub_date is only reached through `-- depends_on` comments; without them buildable drops these tests.
    output = "\n".join(TRADE_BUILD_OUTPUT)
    for test in (
        "relationships_dwd_trade_order_di_order_date_key__date_key__ref_dim_pub_date_",
        "relationships_dwd_trade_order_lifecycle_di_pay_date_key__date_key__ref_dim_pub_date_",
        "relationships_dwd_trade_payment_di_pay_date_key__date_key__ref_dim_pub_date_",
    ):
        assert f"PASS {test}" in output, test
