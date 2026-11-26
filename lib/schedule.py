"""일정 (schedule_events). 모든 함수는 user_id 의 일정만 다뤄요."""
from __future__ import annotations

from datetime import date
from typing import Optional

from lib.db import execute, fetch_all
from lib.models import ScheduleEvent

KIND_LABELS = {"busy": "바쁜 날", "workout": "운동", "guests": "손님", "normal": "기타"}
KIND_ICONS = {"busy": "⏰", "workout": "💪", "guests": "👥", "normal": "📌"}


def validate_event(kind: str, title: Optional[str], guests: Optional[int]) -> tuple[str, Optional[str], Optional[int]]:
    """입력 검사. 잘못되면 ValueError(보여줄 메시지)."""
    if kind not in KIND_LABELS:
        raise ValueError("일정 종류가 올바르지 않아요.")
    title = (title or "").strip() or None
    if title and len(title) > 50:
        raise ValueError("제목이 너무 길어요 (50자 이하).")
    if kind == "guests":
        if not guests or guests < 1 or guests > 30:
            raise ValueError("손님 수를 1~30명으로 입력해 주세요.")
    else:
        guests = None
    return kind, title, guests


def get_events(user_id: str, start: date, end: date) -> list[ScheduleEvent]:
    rows = fetch_all(
        "select id, date, kind, title, guests from schedule_events"
        " where user_id = %s and date between %s and %s order by date, created_at",
        (user_id, start, end),
    )
    return [ScheduleEvent(id=str(r["id"]), date=r["date"], kind=r["kind"], title=r["title"], guests=r["guests"]) for r in rows]


def add_event(user_id: str, day: date, kind: str, title: Optional[str] = None, guests: Optional[int] = None) -> None:
    kind, title, guests = validate_event(kind, title, guests)
    execute(
        "insert into schedule_events (user_id, date, kind, title, guests) values (%s, %s, %s, %s, %s)",
        (user_id, day, kind, title, guests),
    )


def delete_event(user_id: str, event_id: str) -> None:
    execute("delete from schedule_events where id = %s and user_id = %s", (event_id, user_id))


def event_label(e: ScheduleEvent) -> str:
    """예: '👥 손님 4명 · 집들이'"""
    label = f"{KIND_ICONS[e.kind]} {KIND_LABELS[e.kind]}"
    if e.kind == "guests" and e.guests:
        label += f" {e.guests}명"
    return f"{label} · {e.title}" if e.title else label
