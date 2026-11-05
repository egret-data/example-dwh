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


def test_asset_template_rejects_a_collapsed_run_of_two_days_whatever_the_event_order():
    # One dbt_trade run builds one dt. Picking either day would leave the other day's partitions unbuilt, so
    # the template lists every day (oldest first) in a value get_dt rejects: the run fails and the operator
    # reruns each day with conf.dt.
    nov1 = asset_event("dbt_ods_shop", datetime(2026, 10, 31, 17, 0, tzinfo=UTC))
    nov2 = asset_event("dbt_ods_shop", datetime(2026, 11, 1, 17, 0, tzinfo=UTC))

    assert render_asset_template([nov2, nov1]) == "MULTIPLE:2026-11-01,2026-11-02"
    assert render_asset_template([nov1, nov2]) == "MULTIPLE:2026-11-01,2026-11-02"


def test_asset_template_takes_the_day_when_several_events_share_it():
    # One ODS run emits an event per table, and two ODS DAGs can run for the same night.
    orders = asset_event("dbt_ods_shop", datetime(2026, 11, 1, 17, 0, tzinfo=UTC))
    shops = asset_event("dbt_ods_shop", datetime(2026, 11, 1, 17, 0, tzinfo=UTC))
    other = asset_event("dbt_ods_crm", datetime(2026, 11, 1, 17, 30, tzinfo=UTC))

    assert render_asset_template([orders, shops, other]) == "2026-11-02"


def sdk_event(source_dag_id, interval_start, conf=None, run_id="run"):
    """A real SDK triggering event whose source run is a real SDK DagRun (as fetched from the supervisor)."""
    from airflow.sdk.api.datamodels._generated import (
        AssetReferenceAssetEventDagRun,
        DagRun,
        DagRunState,
        DagRunType,
    )
    from airflow.sdk.execution_time.comms import AssetEventDagRunReferenceResult

    event = AssetEventDagRunReferenceResult(
        asset=AssetReferenceAssetEventDagRun(name="a", uri="trino://t:8080/iceberg/dev_ods/x", extra={}),
        extra={},
        source_task_id="t",
        source_dag_id=source_dag_id,
        source_run_id=run_id,
        source_map_index=-1,
        source_aliases=[],
        timestamp=interval_start,
    )
    run = DagRun(
        dag_id=source_dag_id,
        run_id=run_id,
        logical_date=interval_start,
        data_interval_start=interval_start,
        data_interval_end=interval_start,
        run_after=interval_start,
        start_date=interval_start,
        end_date=None,
        run_type=DagRunType.MANUAL if conf else DagRunType.SCHEDULED,
        state=DagRunState.SUCCESS,
        consumed_asset_events=[],
        partition_key=None,
        conf=conf,
    )
    event.__dict__["source_dag_run"] = run  # what the cached_property would fetch from the supervisor
    return event


NOV2_RUN = datetime(2026, 11, 1, 17, 0, tzinfo=UTC)  # 00:00 VN of 2026-11-02: a scheduled ODS run for 11-02


def test_asset_template_takes_a_manual_ods_runs_conf_dt():
    manual_ods = sdk_event("dbt_ods_shop", datetime(2026, 11, 5, 3, 0, tzinfo=UTC), conf={"dt": "2026-10-20"})

    assert render_asset_template([manual_ods]) == "2026-10-20"


def test_asset_template_rejects_an_ods_conf_dt_collapsed_with_another_day():
    # An ODS conf.dt and a scheduled interval day are both candidates: neither may silently win.
    scheduled = sdk_event("dbt_ods_shop", NOV2_RUN, run_id="s")
    oct21 = sdk_event("dbt_ods_shop", NOV2_RUN, conf={"dt": "2026-10-21"}, run_id="m1")
    oct20 = sdk_event("dbt_ods_shop", NOV2_RUN, conf={"dt": "2026-10-20"}, run_id="m2")

    assert render_asset_template([scheduled, oct21, oct20]) == "MULTIPLE:2026-10-20,2026-10-21,2026-11-02"
    assert render_asset_template([oct20, scheduled]) == "MULTIPLE:2026-10-20,2026-11-02"


def test_asset_template_takes_an_ods_conf_dt_equal_to_the_interval_day():
    scheduled = sdk_event("dbt_ods_shop", NOV2_RUN, run_id="s")
    manual = sdk_event("dbt_ods_shop", NOV2_RUN, conf={"dt": "2026-11-02"}, run_id="m")

    assert render_asset_template([manual, scheduled]) == "2026-11-02"


def test_asset_template_own_conf_dt_beats_a_collapsed_run():
    nov1 = sdk_event("dbt_ods_shop", datetime(2026, 10, 31, 17, 0, tzinfo=UTC), run_id="a")
    nov2 = sdk_event("dbt_ods_shop", NOV2_RUN, run_id="b")

    assert render_asset_template([nov1, nov2], conf={"dt": "2026-11-01"}) == "2026-11-01"


def test_asset_template_ignores_a_manual_dbt_pub_runs_conf_dt():
    # dbt_trade's AND schedule keeps a manual dbt_pub run's events queued until the next night's ODS events.
    # The night's run must build the ODS day, not the old day of that manual dbt_pub run.
    manual_pub = sdk_event("dbt_pub", datetime(2026, 11, 1, 3, 0, tzinfo=UTC), conf={"dt": "2026-10-01"})
    scheduled_ods = sdk_event("dbt_ods_shop", NOV2_RUN)

    assert render_asset_template([manual_pub, scheduled_ods]) == "2026-11-02"
    assert render_asset_template([manual_pub]) == ""


def test_asset_template_own_conf_dt_beats_a_producer_conf_dt():
    manual_ods = sdk_event("dbt_ods_shop", NOV2_RUN, conf={"dt": "2026-10-20"})

    assert render_asset_template([manual_ods], conf={"dt": "2026-10-25"}) == "2026-10-25"
