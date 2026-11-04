"""D12: dt is the Asia/Ho_Chi_Minh day of the run's data interval, never Airflow's UTC `ds`."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pendulum
import pytest
from airflow.timetables.interval import CronDataIntervalTimetable
from jinja2 import Template

from _common.dates import ASSET_DT_TEMPLATE, BUSINESS_TZ, DT_TEMPLATE, daily_vn


@pytest.mark.parametrize(
    ("start_utc", "expected"),
    [
        (pendulum.datetime(2026, 11, 1, 17, 0, tz="UTC"), "2026-11-02"),  # 00:00 VN
        (pendulum.datetime(2026, 11, 2, 16, 59, tz="UTC"), "2026-11-02"),  # 23:59 VN
        (pendulum.datetime(2026, 11, 2, 17, 0, tz="UTC"), "2026-11-03"),  # next VN day
    ],
)
def test_dt_template_renders_the_vietnam_day(start_utc, expected):
    assert (
        Template(DT_TEMPLATE).render(data_interval_start=start_utc, dag_run=SimpleNamespace(conf={}))
        == expected
    )


def test_conf_dt_overrides_the_data_interval_day():
    start = pendulum.datetime(2026, 11, 1, 17, 0, tz="UTC")
    rendered = Template(DT_TEMPLATE).render(
        data_interval_start=start, dag_run=SimpleNamespace(conf={"dt": "2026-10-30"})
    )
    assert rendered == "2026-10-30"


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


def asset_event(source_dag_id, interval_start):
    """A triggering event as the SDK exposes it: the source run carries plain, timezone-aware datetimes."""
    return SimpleNamespace(
        source_dag_id=source_dag_id, source_dag_run=SimpleNamespace(data_interval_start=interval_start)
    )


def render_asset_template(events, conf=None):
    from airflow.sdk.execution_time import macros

    return Template(ASSET_DT_TEMPLATE).render(
        triggering_asset_events={f"asset{i}": [e] for i, e in enumerate(events)},
        dag_run=SimpleNamespace(conf=conf or {}),
        macros=macros,
    )


def test_asset_template_reads_the_vietnam_day_of_the_ods_producer_run():
    ods = asset_event("dbt_ods_shop", datetime(2026, 11, 1, 17, 0, tzinfo=UTC))  # 00:00 VN of 2026-11-02
    # dbt_pub's own interval is the moment it was triggered (the next day); it must not win.
    pub = asset_event("dbt_pub", datetime(2026, 11, 2, 17, 5, tzinfo=UTC))

    assert render_asset_template([pub, ods]) == "2026-11-02"


def test_asset_template_prefers_conf_dt_and_is_empty_without_an_ods_event():
    ods = asset_event("dbt_ods_shop", datetime(2026, 11, 1, 17, 0, tzinfo=UTC))

    assert render_asset_template([ods], conf={"dt": "2026-10-30"}) == "2026-10-30"
    assert render_asset_template([]) == ""


def test_asset_template_renders_the_earliest_day_whatever_the_event_order():
    # Several dbt_ods_shop runs can collapse into one asset-triggered run; event DWDs read every ODS partition
    # from dt on, so the earliest day is the safe one. A later day would skip the days before it.
    nov1 = asset_event("dbt_ods_shop", datetime(2026, 10, 31, 17, 0, tzinfo=UTC))
    nov2 = asset_event("dbt_ods_shop", datetime(2026, 11, 1, 17, 0, tzinfo=UTC))

    assert render_asset_template([nov2, nov1]) == "2026-11-01"
    assert render_asset_template([nov1, nov2]) == "2026-11-01"
