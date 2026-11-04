import pytest

from dwh.rules.metrics import metric_column
from fixtures.manifest import good_project


@pytest.mark.parametrize(
    ("derived", "atomic", "expected"),
    [
        ({"period": "1d"}, {"name": "order_amt", "aggregation": "sum"}, "order_amt_sum_1d"),
        (
            {"period": "nd", "days": 30, "modifiers": ["app"]},
            {"name": "order_amt", "aggregation": "sum"},
            "app_order_amt_sum_30d",
        ),
        ({"period": "td"}, {"name": "order", "aggregation": "count"}, "order_cnt_td"),
        ({"period": "1d"}, {"name": "order_buyer", "aggregation": "count_distinct"}, "order_buyer_dcnt_1d"),
    ],
)
def test_metric_column_template(derived, atomic, expected):
    assert metric_column(derived, atomic) == expected


def column(name, metric):
    return {"name": name, "description": "A metric.", "meta": {"metric": metric}}


def test_good_project_has_no_m_findings(lint):
    builder, _ = good_project()
    assert lint(builder, prefix="DWH-M") == []


def test_m01_derived_metric_name_must_follow_the_template(lint):
    builder, _ = good_project()

    def mutate(files):
        files["metrics"]["derived"][1]["name"] = "app_order_amt_30d"

    assert lint(builder, mutate=mutate, prefix="DWH-M") == ["DWH-M01"]


def test_m02_derived_metric_on_a_non_additive_atomic(lint):
    builder, _ = good_project()

    def mutate(files):
        files["metrics"]["derived"].append(
            {
                "name": "order_buyer_dcnt_1d",
                "atomic": "order_buyer",
                "period": "1d",
                "grain": ["customer"],
                "description": "Distinct buyers.",
            }
        )

    assert lint(builder, mutate=mutate, prefix="DWH-M") == ["DWH-M02"]


def test_m03_dws_column_that_is_not_grain_dt_or_metric(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["city"] = {
        "name": "city",
        "description": "City.",
        "meta": {},
    }
    assert lint(builder, prefix="DWH-M") == ["DWH-M03"]


def test_m03_dws_must_declare_its_grain(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["meta"].pop("grain")
    # The model itself, and customer_key which is no longer a declared grain column.
    assert lint(builder, prefix="DWH-M") == ["DWH-M03", "DWH-M03"]


def test_m04_metric_column_must_be_named_after_its_metric(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["order_cnt_1d"]["meta"]["metric"] = "order_amt_sum_1d"
    assert lint(builder, prefix="DWH-M") == ["DWH-M04"]


def test_m04_ads_metric_must_exist(lint):
    builder, ids = good_project()
    builder.node(ids["ads_customer"])["columns"]["avg_order_amt_1d"]["meta"]["metric"] = "avg_gmv_1d"
    assert lint(builder, prefix="DWH-M") == ["DWH-M04"]


def test_m05_one_period_per_dws_table(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["app_order_amt_sum_30d"] = column(
        "app_order_amt_sum_30d", "app_order_amt_sum_30d"
    )
    assert lint(builder, prefix="DWH-M") == ["DWH-M05"]


def test_m06_calculated_metric_must_not_be_stored_in_dws(lint):
    builder, ids = good_project()
    builder.node(ids["dws_customer"])["columns"]["avg_order_amt_1d"] = column(
        "avg_order_amt_1d", "avg_order_amt_1d"
    )
    assert lint(builder, prefix="DWH-M") == ["DWH-M06"]
