"""장보기 목록 계산 — 순수 함수.

이번 주 식단 레시피의 재료 합계 − 지금 재고 = 사야 할 것 (PLAN.md 5장 ⑦).
- 같은 재료는 합쳐요 (g↔kg, ml↔L 환산).
- 재고가 있는데 단위가 달라 비교할 수 없으면(예: 필요 20g, 재고 1모) 있는 것으로 봐요.
- 선택 재료와 물은 빼요.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from lib.catalog import match_catalog
from lib.cooking_rules import convert, same_ingredient
from lib.models import CatalogItem, InventoryItem, Recipe

IGNORED = {"물", "정수물", "생수"}


@dataclass
class ShoppingNeed:
    name: str
    quantity: Optional[float]
    unit: Optional[str]
    recipes: list[str] = field(default_factory=list)


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def build_shopping_list(
    meals: list[tuple[Recipe, Optional[int]]],
    inventory: list[InventoryItem],
    catalog: list[CatalogItem],
) -> list[ShoppingNeed]:
    # 1) 필요한 양 합치기 (같은 재료 = 카탈로그 이름 기준, 단위는 처음 나온 것으로 환산)
    needs: dict[str, ShoppingNeed] = {}
    for recipe, servings in meals:
        scale = (servings / recipe.servings) if (servings and recipe.servings) else 1.0
        for ing in recipe.ingredients:
            if ing.optional or _norm(ing.name) in {_norm(x) for x in IGNORED}:
                continue
            cat = match_catalog(ing.name, catalog)
            key = _norm(cat.name if cat else ing.name)
            qty = ing.qty * scale if ing.qty else None
            if key not in needs:
                needs[key] = ShoppingNeed(cat.name if cat else ing.name, qty, ing.unit, [recipe.title])
                continue
            need = needs[key]
            if recipe.title not in need.recipes:
                need.recipes.append(recipe.title)
            if qty is None or need.quantity is None:
                continue
            converted = convert(qty, ing.unit, need.unit)
            if converted is not None:
                need.quantity += converted

    # 2) 재고 빼기
    active = [i for i in inventory if i.status == "active" and i.quantity > 0]
    out: list[ShoppingNeed] = []
    for need in needs.values():
        stock = [i for i in active if same_ingredient(need.name, i, catalog)]
        if not stock:
            out.append(need)
            continue
        if need.quantity is None:
            continue  # 양 모르는 재료가 재고에 있으면 충분하다고 봐요
        have, comparable = 0.0, True
        for item in stock:
            c = convert(item.quantity, item.unit, need.unit)
            if c is None:
                comparable = False
                break
            have += c
        if not comparable:
            continue
        short = need.quantity - have
        if short > 1e-9:
            out.append(ShoppingNeed(need.name, round(short, 2), need.unit, need.recipes))
    return sorted(out, key=lambda n: n.name)
