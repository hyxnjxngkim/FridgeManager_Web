""""이거 만들게" 재고 빼기 계획 — 순수 함수 (DB 없이 테스트 가능).

레시피 재료를 재고와 맞춰서 무엇을 얼마나 뺄지 '제안'만 해요.
사용자가 화면에서 양을 고친 뒤 확정하면 lib/cooking.py 가 실제로 빼요.

규칙
- 같은 재료가 여러 개면 유통기한이 빠른 것부터 빼요 (FEFO).
- 단위가 같거나 환산되면(g↔kg, ml↔L) 레시피 양만큼 (인분에 맞춰 배수).
- 단위가 다르면: 개수 단위(개·모·단 …) 재고는 1개, 그 밖에는 0 (직접 입력).
- 양념·오래가는 재료(보통 보관 60일 이상)는 기본 0 — 한 번에 다 쓰지 않으니까요.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from lib.catalog import match_catalog
from lib.models import CatalogItem, InventoryItem, Recipe

COUNT_UNITS = {"개", "모", "단", "봉", "팩", "마리", "줄", "통", "캔", "병", "알", "쪽", "장", "대"}
# 같은 종류끼리 환산: 단위 → (종류, 기준 단위로 몇 배)
CONVERTIBLE = {"g": ("무게", 1), "kg": ("무게", 1000), "ml": ("부피", 1), "l": ("부피", 1000)}
LONG_LASTING_DAYS = 60
RESCUE_DAYS = 3


@dataclass
class DeductionLine:
    item_id: str
    item_name: str
    ingredient: str
    available: float
    unit: Optional[str]
    amount: float  # 제안하는 뺄 양 (재고 단위)
    expires_at: date
    days_left: int
    note: str = ""

    @property
    def is_rescue(self) -> bool:
        return 0 <= self.days_left <= RESCUE_DAYS


@dataclass
class CookPlan:
    recipe_id: str
    recipe_title: str
    servings: Optional[int]
    lines: list[DeductionLine] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # 재고에 없는 필수 재료

    def rescued_count(self) -> int:
        """이번 요리로 구출하는 임박 재료 수 (뺄 양이 있는 것만)."""
        return len({ln.item_id for ln in self.lines if ln.amount > 0 and ln.is_rescue})


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _same_ingredient(ingredient: str, item: InventoryItem, catalog: list[CatalogItem]) -> bool:
    match = match_catalog(ingredient, catalog)
    if match and item.catalog_id == match.id:
        return True
    if _norm(ingredient) == _norm(item.name):
        return True
    item_match = match_catalog(item.name, catalog)
    return bool(match and item_match and match.id == item_match.id)


def convert(qty: float, from_unit: Optional[str], to_unit: Optional[str]) -> Optional[float]:
    """from_unit 의 qty 를 to_unit 으로 바꾼 값. 같은 단위면 그대로, 환산 못 하면 None."""
    a, b = _norm(from_unit), _norm(to_unit)
    if a == b:
        return qty
    if a in CONVERTIBLE and b in CONVERTIBLE and CONVERTIBLE[a][0] == CONVERTIBLE[b][0]:
        return qty * CONVERTIBLE[a][1] / CONVERTIBLE[b][1]
    return None


def _round(x: float) -> float:
    return round(x, 2)


def plan_cook(
    recipe: Recipe,
    inventory: list[InventoryItem],
    catalog: list[CatalogItem],
    today: date,
    servings: Optional[int] = None,
) -> CookPlan:
    scale = 1.0
    if servings and recipe.servings:
        scale = servings / recipe.servings
    plan = CookPlan(recipe.id, recipe.title, servings or recipe.servings)
    active = sorted(
        (i for i in inventory if i.status == "active" and i.quantity > 0),
        key=lambda i: (i.expires_at, i.name),
    )
    used_ids: set[str] = set()

    for ing in recipe.ingredients:
        candidates = [i for i in active if i.id not in used_ids and _same_ingredient(ing.name, i, catalog)]
        if not candidates:
            if not ing.optional:
                plan.missing.append(ing.name)
            continue

        cat = match_catalog(ing.name, catalog) or match_catalog(candidates[0].name, catalog)
        long_lasting = bool(cat and cat.default_shelf_days >= LONG_LASTING_DAYS)
        need = ing.qty * scale if ing.qty else None
        # 레시피 양을 재고 단위로 환산 (같은 단위면 그대로, 못 하면 None)
        need = convert(need, ing.unit, candidates[0].unit) if need is not None else None

        if long_lasting:
            first = candidates[0]
            plan.lines.append(_line(first, ing.name, 0, today, "양념·오래가는 재료라 기본 0"))
            used_ids.add(first.id)
            continue

        if need is not None:
            remaining = need
            for item in candidates:
                if remaining <= 0:
                    break
                amount = min(item.quantity, remaining)
                remaining -= amount
                plan.lines.append(_line(item, ing.name, amount, today))
                used_ids.add(item.id)
            if remaining > 1e-9:
                plan.lines[-1].note = f"레시피보다 {_round(remaining)}{candidates[0].unit or ''} 부족해요"
            continue

        first = candidates[0]
        if (first.unit or "") in COUNT_UNITS:
            amount = min(1.0, first.quantity)
            note = f"단위가 달라 1{first.unit} 빼는 것으로 추정" if ing.unit else f"1{first.unit} 빼는 것으로 추정"
        else:
            amount, note = 0.0, "단위가 달라 직접 입력해 주세요"
        plan.lines.append(_line(first, ing.name, amount, today, note))
        used_ids.add(first.id)

    return plan


def _line(item: InventoryItem, ingredient: str, amount: float, today: date, note: str = "") -> DeductionLine:
    return DeductionLine(
        item_id=item.id,
        item_name=item.name,
        ingredient=ingredient,
        available=item.quantity,
        unit=item.unit,
        amount=_round(amount),
        expires_at=item.expires_at,
        days_left=(item.expires_at - today).days,
        note=note,
    )


def summarize_plan(plan: CookPlan) -> str:
    """에이전트에게 돌려줄 짧은 요약."""
    parts = [f"{ln.item_name} {ln.amount:g}{ln.unit or ''}" for ln in plan.lines if ln.amount > 0]
    text = f"'{plan.recipe_title}' 재고 빼기 미리보기를 화면에 띄웠어요."
    text += f" 뺄 재료: {', '.join(parts) if parts else '없음'}."
    if plan.missing:
        text += f" 재고에 없는 재료: {', '.join(plan.missing)}."
    text += f" 구출되는 임박 재료 {plan.rescued_count()}개. 사용자가 화면에서 확인해야 실제로 빠져요."
    return text
