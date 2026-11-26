"""주간 식단 짜기 — 순수 함수 (Claude 없이 코드 규칙으로, 비용 0).

PLAN.md 5장 ④ 규칙
- 바쁜 날(busy)   → 15분 이하 요리
- 운동한 날(workout) → '고단백' 태그 가산
- 손님 오는 날(guests) → 손님 수 + 나 만큼 인분
- 임박 재료가 이른 날짜에 오도록: 그날까지 괜찮은 임박 재료 중 유통기한이 빠른 것부터 검색
- 같은 메뉴는 한 주에 한 번만 (레시피가 모자라면 그때만 반복)
- 임박 재료로 고를 게 없으면(다 쓴 날 등) 냉장고의 다른 재료로 검색해요.
  B의 검색은 재료 목록이 비면 결과가 없어서, 이게 없으면 임박 재료를 다 쓴 뒤의 날이 비어요.

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


def _names_for(items: list[InventoryItem], day: date, skip: set[str]) -> list[str]:
    """그날에도 괜찮은 재료 이름, 유통기한 빠른 순, 중복 없이 최대 5개."""
    names = [i.name for i in items if i.expires_at >= day and i.name not in skip]
    return list(dict.fromkeys(names))[:MAX_SEARCH_INGREDIENTS]


def plan_week(
    start: date,
    events: list[ScheduleEvent],
    expiring: list[InventoryItem],
    search: Search,
    days: int = 7,
    stock: Optional[list[InventoryItem]] = None,
) -> list[PlannedMeal]:
    """stock: 냉장고 전체 재고 (임박 재료로 못 고를 때 대신 검색할 재료)."""
    rescued: set[str] = set()  # 이미 식단에 넣은 임박 재료
    used_ids: set[str] = set()
    plan: list[PlannedMeal] = []
    by_expiry = sorted(expiring, key=lambda i: (i.expires_at, i.name))
    expiring_names = {i.name for i in expiring}
    stock_by_expiry = sorted(stock or [], key=lambda i: (i.expires_at, i.name))

    for offset in range(days):
        day = start + timedelta(days=offset)
        rule = day_rule(day, events)
        args = (rule.max_minutes, rule.servings, rule.tags or None)

        # 1) 그날에도 괜찮고 아직 식단에 안 들어간 임박 재료로
        names = _names_for(by_expiry, day, rescued)
        matches = search(names, *args)  # 재료가 비어도 불러요 (운동한 날 '고단백' 태그만으로도 찾을 수 있게)
        fresh = [m for m in matches if m.recipe.id not in used_ids]
        pick = next((m for m in fresh if m.uses_expiring), None)
        from_stock = False

        # 2) 못 고르면 냉장고의 다른 재료로
        if pick is None:
            others = _names_for(stock_by_expiry, day, set(names))
            if others:
                more = search(others, *args)
                fresh_more = [m for m in more if m.recipe.id not in used_ids]
                if fresh_more:
                    pick, from_stock = fresh_more[0], True
                matches = matches or more

        # 3) 그래도 없으면 남은 결과 중 하나, 그것도 다 썼으면 반복
        repeated = False
        if pick is None and fresh:
            pick = fresh[0]
        if pick is None and matches:
            pick, repeated = matches[0], True

        reasons = list(rule.labels)
        if pick is None:
            plan.append(PlannedMeal(day, None, rule.servings, " · ".join(reasons + ["조건에 맞는 레시피가 없어요"])))
            continue
        used_ids.add(pick.recipe.id)
        saved = [] if from_stock else [n for n in pick.uses_expiring if n in expiring_names]
        rescued |= set(saved)
        if saved:
            reasons.append("구출: " + ", ".join(saved))
        elif from_stock and pick.uses_expiring:
            reasons.append("냉장고 재료: " + ", ".join(pick.uses_expiring))
        if repeated:
            reasons.append("레시피가 모자라 반복")
        plan.append(PlannedMeal(day, pick, rule.servings or pick.recipe.servings, " · ".join(reasons) or "평소 메뉴"))
    return plan
