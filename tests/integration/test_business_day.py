"""in_business_day_tz(): the Vietnam-day window on a timestamp(6) with time zone column (STD-05-08)."""

from helpers import MAIN_PROJECT, query, run_dbt


def test_in_business_day_tz_keeps_exactly_the_vietnam_day():
    compiled = run_dbt(
        MAIN_PROJECT,
        ["--quiet", "compile", "--inline", "{{ in_business_day_tz('ts') }}", "--vars", "{dt: '2026-11-02'}"],
        "itest_bday",
    )

    rows = query(
        "SELECT name FROM (VALUES "
        "('before', TIMESTAMP '2026-11-01 16:59:59.999999 UTC'), "
        "('start', TIMESTAMP '2026-11-01 17:00:00.000000 UTC'), "
        "('last', TIMESTAMP '2026-11-02 23:59:59.999999 Asia/Ho_Chi_Minh'), "
        "('next', TIMESTAMP '2026-11-03 00:00:00.000000 Asia/Ho_Chi_Minh')"
        f") AS t (name, ts) WHERE {compiled.strip()} ORDER BY name"
    )

    assert rows == [("last",), ("start",)]
