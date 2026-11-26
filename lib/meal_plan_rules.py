"""주간 식단 짜기 — 순수 함수 (Claude 없이 코드 규칙으로, 비용 0).

PLAN.md 5장 ④ 규칙
- 바쁜 날(busy)   → 15분 이하 요리
- 운동한 날(workout) → '고단백' 태그 가산
- 손님 오는 날(guests) → 손님 수 + 나 만큼 인분
- 임박 재료가 이른 날짜에 오도록: 그날까지 괜찮은 임박 재료 중 유통기한이 빠른 것부터 검색
- 같은 메뉴는 한 주에 한 번만 (레시피가 모자라면 그때만 반복)

레시피 검색은 search(재료, max_minutes, servings, tags) 함수를 받아서 써요 (테스트에서 가짜로 바꿀 수 있게).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

from lib.models import InventoryItem, RecipeMatch, ScheduleEvent

WEEKDAYS = "월화수목금토일"
BUSY_MAX_MINUTES = 15
MAX_SEARCH_INGREDIENTS = 5

Search = Callable[[list[str], Optional[int], Optional[int], Optional[list[str]]], list[RecipeMatch]]


@dataclass
class DayRule:
    day: date
    max_minutes: Optional[int] = None
    servings: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class PlannedMeal:
    day: date
    match: Optional[RecipeMatch]
    servings: Optional[int]
    reason: str


def day_label(d: date) -> str:
    """예: '11/26(목)'"""
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def day_rule(day: date, events: list[ScheduleEvent]) -> DayRule:
    rule = DayRule(day)
    for e in events:
        if e.date != day:
            continue
        if e.kind == "busy":
            rule.max_minutes = BUSY_MAX_MINUTES
            rule.labels.append(f"바쁜 날 → {BUSY_MAX_MINUTES}분 요리")
        elif e.kind == "workout":
            if "고단백" not in rule.tags:
                rule.tags.append("고단백")
            rule.labels.append("운동 → 고단백")
        elif e.kind == "guests" and e.guests:
            rule.servings = max(rule.servings or 0, e.guests + 1)
            rule.labels.append(f"손님 {e.guests}명 → {e.guests + 1}인분")
    return rule


def plan_week(
    start: date,
    events: list[ScheduleEvent],
    expiring: list[InventoryItem],
    search: Search,
    days: int = 7,
) -> list[PlannedMeal]:
    rescued: set[str] = set()  # 이미 식단에 넣은 임박 재료
    used_ids: set[str] = set()
    plan: list[PlannedMeal] = []
    by_expiry = sorted(expiring, key=lambda i: (i.expires_at, i.name))

    for offset in range(days):
        day = start + timedelta(days=offset)
        rule = day_rule(day, events)
        # 그날에도 아직 괜찮고, 아직 식단에 안 들어간 임박 재료 (유통기한 빠른 순)
        usable = [i.name for i in by_expiry if i.expires_at >= day and i.name not in rescued]
        names = list(dict.fromkeys(usable))[:MAX_SEARCH_INGREDIENTS]
        matches = search(names, rule.max_minutes, rule.servings, rule.tags or None)

        fresh = [m for m in matches if m.recipe.id not in used_ids]
        pick = next((m for m in fresh if m.uses_expiring), None) or (fresh[0] if fresh else None)
        repeated = False
        if pick is None and matches:
            pick, repeated = matches[0], True

        reasons = list(rule.labels)
        if pick is None:
            plan.append(PlannedMeal(day, None, rule.servings, " · ".join(reasons + ["조건에 맞는 레시피가 없어요"])))
            continue
        used_ids.add(pick.recipe.id)
        rescued |= set(pick.uses_expiring)
        if pick.uses_expiring:
            reasons.append("구출: " + ", ".join(pick.uses_expiring))
        if repeated:
            reasons.append("레시피가 모자라 반복")
        plan.append(PlannedMeal(day, pick, rule.servings or pick.recipe.servings, " · ".join(reasons) or "평소 메뉴"))
    return plan
