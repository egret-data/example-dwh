"""The business day `dt` (spec D12): the Asia/Ho_Chi_Minh calendar day of a run's data interval."""

import pendulum
from airflow.timetables.interval import CronDataIntervalTimetable

BUSINESS_TZ = "Asia/Ho_Chi_Minh"

# Rendered by Airflow at run time. Never `{{ ds }}`: that is the UTC date of the logical date and is
# one day off for a midnight-VN schedule.
DT_TEMPLATE = "{{ data_interval_start.in_timezone('" + BUSINESS_TZ + "').strftime('%Y-%m-%d') }}"


def daily_vn() -> CronDataIntervalTimetable:
    """Runs at 00:00 Asia/Ho_Chi_Minh; each run covers the previous VN day [00:00, 24:00)."""
    return CronDataIntervalTimetable("0 0 * * *", timezone=BUSINESS_TZ)


def vn_date(year: int, month: int, day: int) -> pendulum.DateTime:
    return pendulum.datetime(year, month, day, tz=BUSINESS_TZ)
