"""The business day `dt` (spec D12): the Asia/Ho_Chi_Minh calendar day of a run's data interval."""

import pendulum
from airflow.timetables.interval import CronDataIntervalTimetable

BUSINESS_TZ = "Asia/Ho_Chi_Minh"

# Rendered by Airflow at run time. Never `{{ ds }}`: that is the UTC date of the logical date and is
# one day off for a midnight-VN schedule. `dag_run.conf["dt"]` overrides the day for manual runs and
# backfills.
DT_TEMPLATE = (
    "{{ (dag_run.conf or {}).get('dt') or data_interval_start.in_timezone('"
    + BUSINESS_TZ
    + "').strftime('%Y-%m-%d') }}"
)

# For a DAG scheduled on Assets. Such a run has no cron data interval of its own (AssetTriggeredTimetable
# schedules nothing and a run's interval is the moment it was created), so dt is read from the triggering
# events of `dbt_ods_*` DAGs:
#   1. this run's own `conf.dt` (a manual run) wins outright;
#   2. otherwise each `dbt_ods_*` producer run gives one candidate day: its `conf.dt` (a manual ODS run for a
#      past day reaches its consumers this way), else the business day of its cron data interval (spec D12).
# One candidate day (however many events carry it) is dt. Several producer runs of different days can
# collapse into one run of this DAG (a failed night, a failed ODS task, a ranged ODS backfill). One run builds
# exactly one dt, and an event DWD keeps only rows of that day, so picking any one day would leave the others
# unbuilt with nothing failing. The template then renders `MULTIPLE:<day>,<day>` (oldest first), which get_dt
# rejects: the run fails and the operator reruns each listed day with conf.dt, oldest first (STD-11-03).
# The SDK's source_dag_run carries plain datetimes, hence astimezone rather than pendulum's in_timezone.
# Events of other producers (dbt_pub) are ignored, conf.dt included: their own interval is not a business
# day. Measured live (docs/en/verification/2026-11-05-plan4-followups.md): dbt_trade's AND schedule keeps a
# manual dbt_pub run's events queued until the next night's ODS events, so honouring that run's conf.dt would
# rebuild the old day, not the new one; the ranged ODS backfill renders MULTIPLE and fails as intended.
# A run with no candidate renders an empty dt, which dbt rejects at once (get_dt validates it).
ASSET_DT_TEMPLATE = (
    "{% set found = namespace(days=[]) %}"
    "{% for events in triggering_asset_events.values() %}{% for event in events %}"
    "{% if (event.source_dag_id or '').startswith('dbt_ods_') and event.source_dag_run %}"
    "{% set run = event.source_dag_run %}"
    "{% set day = (run.conf or {}).get('dt') or run.data_interval_start"
    ".astimezone(macros.dateutil.tz.gettz('" + BUSINESS_TZ + "')).strftime('%Y-%m-%d') %}"
    "{% if day not in found.days %}{% set found.days = found.days + [day] %}{% endif %}"
    "{% endif %}{% endfor %}{% endfor %}"
    "{% set days = found.days | sort %}"
    "{{ (dag_run.conf or {}).get('dt') or (days | first if days | length == 1 else "
    "('MULTIPLE:' ~ days | join(',') if days else '')) }}"
)


def daily_vn() -> CronDataIntervalTimetable:
    """Runs at 00:00 Asia/Ho_Chi_Minh; each run covers the previous VN day [00:00, 24:00)."""
    return CronDataIntervalTimetable("0 0 * * *", timezone=BUSINESS_TZ)


def vn_date(year: int, month: int, day: int) -> pendulum.DateTime:
    return pendulum.datetime(year, month, day, tz=BUSINESS_TZ)
