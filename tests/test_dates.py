from datetime import date, datetime, timezone

from lib.dates import add_days, d_day_label, days_between, expiry_level, parse_date, today_kst


def test_add_days_crosses_month_and_year():
    assert add_days(date(2026, 11, 26), 5) == date(2026, 12, 1)
    assert add_days(date(2026, 12, 30), 3) == date(2027, 1, 2)
    assert add_days(date(2028, 2, 28), 1) == date(2028, 2, 29)


def test_days_between():
    assert days_between(date(2026, 11, 26), date(2026, 11, 29)) == 3
    assert days_between(date(2026, 11, 26), date(2026, 11, 24)) == -2


def test_expiry_level_thresholds():
    assert [expiry_level(d) for d in (-1, 0, 1, 2, 3, 4)] == [
        "expired", "urgent", "urgent", "soon", "soon", "ok",
    ]


def test_d_day_label():
    assert [d_day_label(d) for d in (-2, 0, 3)] == ["2일 지남", "D-day", "D-3"]


def test_today_is_korean_date_even_on_foreign_server():
    # UTC 11-26 16:00 = 한국 11-27 01:00
    assert today_kst(datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)) == date(2026, 11, 27)
    assert today_kst(datetime(2026, 11, 26, 14, 59, tzinfo=timezone.utc)) == date(2026, 11, 26)


def test_parse_date_accepts_db_strings_and_dates():
    assert parse_date("2026-11-26") == date(2026, 11, 26)
    assert parse_date(date(2026, 11, 26)) == date(2026, 11, 26)
    assert parse_date(datetime(2026, 11, 26, 9, 0)) == date(2026, 11, 26)
