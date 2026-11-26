"""레시피 검색 연결점 — Phase 4(A)는 이 파일을 통해서만 레시피를 찾아요.

B의 lib/recipes.search_recipes() (Phase 3)를 부르고, 그 결과에서 알레르기 재료가 든 레시피를
**한 번 더** 걸러요. B의 검색도 알레르기를 거르기로 약속돼 있지만(PLAN 5장 ③),
알레르기는 실수하면 위험해서 에이전트 쪽에서도 막아요 (이중 안전장치).
"""
from __future__ import annotations

import re
from typing import Optional

from lib import recipes
from lib.models import RecipeMatch

# 사용자가 말하는 이름 ↔ 레시피의 알레르기 성분 표기 (식품 알레르기 표시 기준 이름)
ALLERGEN_GROUPS: list[set[str]] = [
    {"알류", "달걀", "계란", "메추리알", "난류"},
    {"우유", "유제품", "치즈", "버터", "생크림", "요거트"},
    {"대두", "콩", "두부", "순두부", "연두부", "된장", "간장"},
    {"밀", "밀가루", "글루텐"},
    {"땅콩"},
    {"호두"},
    {"잣"},
    {"갑각류", "새우", "게", "가재", "칵테일새우"},
    {"조개류", "조개", "굴", "전복", "홍합", "바지락"},
    {"오징어"},
    {"고등어"},
    {"메밀"},
    {"복숭아"},
    {"토마토"},
    {"돼지고기"},
    {"쇠고기", "소고기"},
    {"닭고기"},
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def allergy_terms(allergies: list[str]) -> set[str]:
    """사용자 알레르기 → 같은 그룹 이름까지 넓힌 검사어 (예: '계란' → 알류·달걀·계란…)."""
    terms: set[str] = set()
    for a in allergies:
        key = _norm(a)
        if not key:
            continue
        terms.add(key)
        for group in ALLERGEN_GROUPS:
            if key in {_norm(g) for g in group}:
                terms |= {_norm(g) for g in group}
    return terms


def contains_allergen(match: RecipeMatch, allergies: list[str]) -> bool:
    terms = allergy_terms(allergies)
    if not terms:
        return False
    r = match.recipe
    names = [_norm(x) for x in r.allergens] + [_norm(i.name) for i in r.ingredients]
    # 재료 이름은 '포함'으로 봐요 ('칵테일새우'에 '새우'), 알레르기 표기는 정확히 같을 때
    return any(t == n or (len(t) >= 2 and t in n) for t in terms for n in names)


def filter_allergens(matches: list[RecipeMatch], allergies: list[str]) -> list[RecipeMatch]:
    return [m for m in matches if not contains_allergen(m, allergies)]


def search_recipes(
    user_id: str,
    ingredients: list[str],
    max_minutes: Optional[int] = None,
    servings: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> list[RecipeMatch]:
    from lib.preferences import get_allergies

    matches = recipes.search_recipes(user_id, ingredients, max_minutes=max_minutes, servings=servings, tags=tags)
    return filter_allergens(matches, get_allergies(user_id))
