"""날짜 계산 — 순수 함수만 (Streamlit·DB와 무관해서 테스트하기 쉬움).

기준 시간대는 한국 시간입니다. 서버가 싱가포르에 있어도 '오늘'은 한국 날짜예요.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Seoul")

ExpiryLevel = Literal["expired", "urgent", "soon", "ok"]


def today_kst(now: Optional[datetime] = None) -> date:
    """한국 기준 오늘 날짜."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(APP_TIMEZONE).date()


def parse_date(value) -> date:
    """DB의 'YYYY-MM-DD' 문자열이나 date/datetime/pandas Timestamp 를 date 로."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):  # pandas Timestamp
        return value.date()
    return date.fromisoformat(str(value)[:10])


def days_between(start: date, end: date) -> int:
    """start → end 까지 남은 일수 (end가 과거면 음수)."""
    return (end - start).days


def add_days(d: date, days: int) -> date:
    return d + timedelta(days=days)


def expiry_level(days_left: int) -> ExpiryLevel:
    """PLAN 5-②: D-3 이하 주황(soon), D-1 이하 빨강(urgent), 지남 회색(expired)."""
    if days_left < 0:
        return "expired"
    if days_left <= 1:
        return "urgent"
    if days_left <= 3:
        return "soon"
    return "ok"


def d_day_label(days_left: int) -> str:
    if days_left < 0:
        return f"{-days_left}일 지남"
    if days_left == 0:
        return "D-day"
    return f"D-{days_left}"
