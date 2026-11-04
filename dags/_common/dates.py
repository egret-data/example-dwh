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
# events of `dbt_ods_*` DAGs, in this order:
#   1. this run's own `conf.dt` (a manual run);
#   2. the earliest `conf.dt` of a `dbt_ods_*` producer run (a manual ODS run for a past day reaches its
#      consumers this way);
#   3. the earliest business day of a `dbt_ods_*` producer run's cron data interval (spec D12).
# Several producer runs can collapse into one run of this DAG, and event DWDs read every ODS partition from dt
# on, so the earliest day misses nothing (a later one would skip days); the order of events is not a contract.
# The SDK's source_dag_run carries plain datetimes, hence astimezone rather than pendulum's in_timezone.
# Events of other producers (dbt_pub) are ignored, conf.dt included: their own interval is not a business day,
# and dbt_trade's AND schedule keeps a manual dbt_pub run's events queued until the next night's ODS events,
# so honouring that run's conf.dt would rebuild the old day instead of the new one. A run with none of the
# three renders an empty dt, which dbt rejects at once (get_dt validates it).
ASSET_DT_TEMPLATE = (
    "{% set found = namespace(conf='', day='') %}"
    "{% for events in triggering_asset_events.values() %}{% for event in events %}"
    "{% if (event.source_dag_id or '').startswith('dbt_ods_') and event.source_dag_run %}"
    "{% set run = event.source_dag_run %}"
    "{% set conf_dt = (run.conf or {}).get('dt') or '' %}"
    "{% if conf_dt and (not found.conf or conf_dt < found.conf) %}{% set found.conf = conf_dt %}{% endif %}"
    "{% if not conf_dt %}"
    "{% set day = run.data_interval_start"
    ".astimezone(macros.dateutil.tz.gettz('" + BUSINESS_TZ + "')).strftime('%Y-%m-%d') %}"
    "{% if not found.day or day < found.day %}{% set found.day = day %}{% endif %}"
    "{% endif %}"
    "{% endif %}{% endfor %}{% endfor %}"
    "{{ (dag_run.conf or {}).get('dt') or found.conf or found.day }}"
)


def daily_vn() -> CronDataIntervalTimetable:
    """Runs at 00:00 Asia/Ho_Chi_Minh; each run covers the previous VN day [00:00, 24:00)."""
    return CronDataIntervalTimetable("0 0 * * *", timezone=BUSINESS_TZ)


def vn_date(year: int, month: int, day: int) -> pendulum.DateTime:
    return pendulum.datetime(year, month, day, tz=BUSINESS_TZ)
