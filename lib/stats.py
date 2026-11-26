"""대시보드용 DB 조회. 모든 함수는 user_id 의 기록만 읽어요. 날짜는 한국 시간 기준."""
from __future__ import annotations

from datetime import date
from typing import Optional

from lib.db import fetch_all, fetch_one


def meal_rows(user_id: str, since: Optional[date]) -> list[dict]:
    """요리 기록: day(한국 날짜), rescued, title, rating"""
    return fetch_all(
        "select (cooked_at at time zone 'Asia/Seoul')::date as day, rescued_items as rescued,"
        "       recipe_title as title, rating"
        " from meal_logs where user_id = %s"
        " and (%s::date is null or (cooked_at at time zone 'Asia/Seoul')::date >= %s::date)"
        " order by cooked_at",
        (user_id, since, since),
    )


def discard_days(user_id: str, since: Optional[date]) -> list[date]:
    """버린 재료의 버린 날 (status 를 discarded 로 바꾼 시각 = updated_at)."""
    rows = fetch_all(
        "select (updated_at at time zone 'Asia/Seoul')::date as day from inventory"
        " where user_id = %s and status = 'discarded'"
        " and (%s::date is null or (updated_at at time zone 'Asia/Seoul')::date >= %s::date)",
        (user_id, since, since),
    )
    return [r["day"] for r in rows]


def used_count(user_id: str, since: Optional[date]) -> int:
    row = fetch_one(
        "select count(*) as n from inventory where user_id = %s and status = 'used'"
        " and (%s::date is null or (updated_at at time zone 'Asia/Seoul')::date >= %s::date)",
        (user_id, since, since),
    )
    return int(row["n"]) if row else 0
