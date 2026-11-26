"""대시보드 숫자 계산 — 순수 함수 (DB 없이 테스트 가능)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


def week_start(d: date) -> date:
    """그 주 월요일."""
    return d - timedelta(days=d.weekday())


def rescue_rate(rescued: int, discarded: int) -> Optional[float]:
    """구출률 = 구출 ÷ (구출 + 폐기). 둘 다 0이면 None (아직 기록 없음)."""
    total = rescued + discarded
    return rescued / total if total else None


@dataclass
class WeekPoint:
    week: date  # 월요일
    rescued: int
    discarded: int


def weekly_series(
    meals: list[tuple[date, int]],  # (요리한 날, 구출 수)
    discards: list[date],  # 버린 날
    today: date,
    weeks: int = 8,
) -> list[WeekPoint]:
    """최근 weeks 주(이번 주 포함)의 주별 구출·폐기 수. 기록 없는 주도 0으로 채워요."""
    first = week_start(today) - timedelta(weeks=weeks - 1)
    rescued: dict[date, int] = defaultdict(int)
    discarded: dict[date, int] = defaultdict(int)
    for d, n in meals:
        if d >= first:
            rescued[week_start(d)] += n
    for d in discards:
        if d >= first:
            discarded[week_start(d)] += 1
    return [
        WeekPoint(first + timedelta(weeks=i), rescued[first + timedelta(weeks=i)], discarded[first + timedelta(weeks=i)])
        for i in range(weeks)
    ]


@dataclass
class RecipeStat:
    title: str
    count: int
    likes: int
    dislikes: int


def top_recipes(meals: list[tuple[str, Optional[int]]], limit: int = 5) -> list[RecipeStat]:
    """(요리 이름, 평점) 목록 → 자주 먹은 순 TOP. 같으면 👍 많은 순, 이름 순."""
    stats: dict[str, RecipeStat] = {}
    for title, rating in meals:
        if not title:
            continue
        s = stats.setdefault(title, RecipeStat(title, 0, 0, 0))
        s.count += 1
        if rating is not None and rating > 0:
            s.likes += 1
        elif rating is not None and rating < 0:
            s.dislikes += 1
    return sorted(stats.values(), key=lambda s: (-s.count, -s.likes, s.title))[:limit]
