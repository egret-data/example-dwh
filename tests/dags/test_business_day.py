"""D12: dt is the Asia/Ho_Chi_Minh day of the run's data interval, never Airflow's UTC `ds`."""

import pendulum
import pytest
from airflow.timetables.interval import CronDataIntervalTimetable
from jinja2 import Template

from _common.dates import BUSINESS_TZ, DT_TEMPLATE, daily_vn


@pytest.mark.parametrize(
    ("start_utc", "expected"),
    [
        (pendulum.datetime(2026, 11, 1, 17, 0, tz="UTC"), "2026-11-02"),  # 00:00 VN
        (pendulum.datetime(2026, 11, 2, 16, 59, tz="UTC"), "2026-11-02"),  # 23:59 VN
        (pendulum.datetime(2026, 11, 2, 17, 0, tz="UTC"), "2026-11-03"),  # next VN day
    ],
)
def test_dt_template_renders_the_vietnam_day(start_utc, expected):
    assert Template(DT_TEMPLATE).render(data_interval_start=start_utc) == expected


def test_dt_template_does_not_use_ds():
    assert "ds" not in DT_TEMPLATE.replace("data_interval_start", "")


def test_daily_run_covers_the_previous_vietnam_day():
    interval = daily_vn().infer_manual_data_interval(run_after=pendulum.datetime(2026, 11, 3, tz=BUSINESS_TZ))

    assert interval.start == pendulum.datetime(2026, 11, 2, tz=BUSINESS_TZ)
    assert interval.end == pendulum.datetime(2026, 11, 3, tz=BUSINESS_TZ)


def test_ods_shop_dag_uses_the_vn_timetable_and_dt_template(dagbag):
    dag = dagbag.get_dag("dbt_ods_shop")

    assert isinstance(dag.timetable, CronDataIntervalTimetable)
    interval = dag.timetable.infer_manual_data_interval(run_after=pendulum.datetime(2026, 11, 3, tz="UTC"))
    assert interval.start == pendulum.datetime(2026, 11, 2, tz=BUSINESS_TZ)
    for task in dag.tasks:
        assert task.vars == {"dt": DT_TEMPLATE}, task.task_id
