"""레시피 검색 (Phase 3, 팀원 B) — 팀 공용 함수 search_recipes() (PLAN.md 11-2).

흐름 (PLAN 5장 ③-3 하이브리드 검색)
    1) 임박 재료(+태그)로 검색어를 만들어 임베딩 → pgvector 거리순 상위 30개
       - 이때 SQL 로 알레르기 레시피를 **빼고**(하드 필터), max_minutes 가 있으면 조리 시간도 걸러요
    2) 코드로 점수 매기기 (lib/recipe_rules.py): 임박 재료 사용 수 × 3 + 보유 비율 × 2 + 태그 일치
    3) 점수 순으로 돌려줌

임베딩(Bedrock)을 못 부르면 재료 이름 글자 검색으로 대신해요 (알레르기 제외는 똑같이 해요).
"""
from __future__ import annotations

import logging
from typing import Optional

from lib.allergens import normalize_allergy
from lib.models import Recipe, RecipeIngredient, RecipeMatch
from lib.recipe_rules import has_allergen, rank, score_recipe

log = logging.getLogger(__name__)

CANDIDATES = 30  # 벡터 검색으로 가져올 후보 수

_COLUMNS = "id, title, ingredients, steps, cook_minutes, servings, tags, allergens, image_url"
_FILTERS = (
    " not (allergens && %s::text[])"
    " and (%s::int is null or cook_minutes <= %s::int)"
)
_VECTOR_SQL = (
    f"select {_COLUMNS} from recipes"
    f" where embedding is not null and{_FILTERS}"
    " order by embedding <=> %s::vector limit %s"
)
_TEXT_SQL = (
    f"select {_COLUMNS} from recipes"
    f" where{_FILTERS}"
    " and exists (select 1 from jsonb_array_elements(ingredients) e where e->>'name' ilike any(%s::text[]))"
    " order by title limit %s"
)
_ALLERGY_SQL = "select value from preferences where user_id = %s and kind = 'allergy'"


# ── DB·외부 호출 (테스트에서 가짜로 바꿔 끼워요) ─────────────
def _fetch_all(sql: str, params) -> list[dict]:
    from lib.db import fetch_all

    return fetch_all(sql, params)


def _user_allergies(user_id: str) -> list[str]:
    """preferences(kind='allergy')의 값 → 레시피 allergens 이름 (예: '계란' → '달걀')."""
    names: set[str] = set()
    for row in _fetch_all(_ALLERGY_SQL, (user_id,)):
        names.update(normalize_allergy(row["value"]))
    return sorted(names)


def _user_have(user_id: str) -> list[str]:
    from lib.inventory import get_inventory

    return [i.name for i in get_inventory(user_id)]


def _catalog():
    from lib.inventory import get_catalog

    return get_catalog()


def _embed(text: str) -> str:
    from lib.embeddings import embed_query, to_pgvector

    return to_pgvector(embed_query(text))


def _to_recipe(row: dict) -> Recipe:
    return Recipe(
        id=str(row["id"]),
        title=row["title"],
        ingredients=[
            RecipeIngredient(
                name=i.get("name", ""), qty=i.get("qty"), unit=i.get("unit"), optional=bool(i.get("optional"))
            )
            for i in (row["ingredients"] or [])
        ],
        steps=row["steps"],
        cook_minutes=row["cook_minutes"],
        servings=row["servings"],
        tags=list(row["tags"] or []),
        allergens=list(row["allergens"] or []),
        image_url=row.get("image_url"),
    )


def _candidates(
    query: str, ingredients: list[str], allergies: list[str], max_minutes: Optional[int]
) -> list[Recipe]:
    filters = (allergies, max_minutes, max_minutes)
    try:
        vec = _embed(query)
    except Exception as e:  # Bedrock 설정·권한 문제 등 → 글자 검색으로 대신
        log.warning("레시피 임베딩 검색을 못 해서 글자 검색으로 바꿔요: %s: %s", type(e).__name__, e)
        if not ingredients:
            return []
        patterns = [f"%{name.strip()}%" for name in ingredients if name.strip()]
        rows = _fetch_all(_TEXT_SQL, (*filters, patterns, CANDIDATES))
    else:
        rows = _fetch_all(_VECTOR_SQL, (*filters, vec, CANDIDATES))
    return [_to_recipe(r) for r in rows]


# ── 팀 공용 함수 ─────────────────────────────────────
def search_recipes(
    user_id: str,
    ingredients: list[str],
    max_minutes: Optional[int] = None,
    servings: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> list[RecipeMatch]:
    """임박 재료(ingredients)를 쓰는 레시피를 점수 순으로 (최대 30개).

    - user_id: 이 사용자의 알레르기 레시피는 빼고, 재고로 보유 비율·없는 재료를 계산해요
    - ingredients: 임박 재료 이름 목록, 예: ["두부", "우유"]
    - max_minutes: 주어지면 조리 시간(추정)이 이보다 긴 레시피는 빼요 (바쁜 날은 recipe_rules.BUSY_MAX_MINUTES)
    - servings: 몇 인분인지. 지금 레시피는 모두 1인분이라 받기만 해요 (인분 배수는 Phase 5)
    - tags: 일치하는 태그마다 점수 +1 (예: ["고단백"]). 거르지는 않아요

    ingredients 와 tags 가 둘 다 비어 있으면 빈 목록이에요.
    """
    ingredients = [n for n in (ingredients or []) if n and n.strip()]
    tags = [t for t in (tags or []) if t and t.strip()]
    query = " ".join([*ingredients, *tags])
    if not query:
        return []

    allergies = _user_allergies(user_id)
    recipes = _candidates(query, ingredients, allergies, max_minutes)
    if not recipes:
        return []
    have, catalog = _user_have(user_id), _catalog()
    matches = [
        score_recipe(r, ingredients, have, tags, catalog)
        for r in recipes
        if not has_allergen(r, allergies)  # SQL 로 뺐지만 한 번 더
    ]
    return rank(matches)
