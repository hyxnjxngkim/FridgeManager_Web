"""B의 search_recipes()(Phase 3)가 main 에 들어오기 전까지 쓰는 예시 레시피.

lib/recipe_source.py 가 lib/recipes.py 가 없을 때만 이 파일을 써요.
B의 코드가 합쳐지면 자동으로 진짜 검색으로 바뀌니 이 파일은 그때 지워도 돼요.
함수 모양은 PLAN.md 11-2 약속과 같아요.
"""
from __future__ import annotations

import re
from typing import Optional

from lib.models import Recipe, RecipeIngredient as I, RecipeMatch

SAMPLE_RECIPES: list[Recipe] = [
    Recipe("fake-tofu-braise", "두부조림", [I("두부", 1, "모"), I("대파", 0.5, "대"), I("간장", 3, "큰술"), I("고춧가루", 1, "큰술"), I("다진마늘", 1, "큰술")],
           "1. 두부를 1cm 두께로 썰어 팬에 노릇하게 굽는다.\n2. 간장·고춧가루·다진마늘·물 4큰술로 양념장을 만든다.\n3. 두부에 양념장을 끼얹고 약불로 5분 졸인 뒤 대파를 올린다.",
           cook_minutes=15, servings=2, tags=["반찬", "매운맛"], allergens=["대두"]),
    Recipe("fake-bean-sprout-soup", "콩나물국", [I("콩나물", 200, "g"), I("대파", 0.5, "대"), I("다진마늘", 0.5, "큰술"), I("국간장", 1, "큰술")],
           "1. 물 5컵에 콩나물을 넣고 뚜껑을 덮어 8분 끓인다.\n2. 다진마늘·국간장으로 간하고 대파를 넣어 1분 더 끓인다.",
           cook_minutes=10, servings=2, tags=["국", "10분 요리"], allergens=["대두"]),
    Recipe("fake-spinach-namul", "시금치나물", [I("시금치", 1, "단"), I("참기름", 1, "큰술"), I("다진마늘", 0.5, "큰술"), I("소금", 0.3, "작은술")],
           "1. 시금치를 끓는 소금물에 30초 데친 뒤 찬물에 헹궈 물기를 짠다.\n2. 참기름·다진마늘·소금으로 무친다.",
           cook_minutes=10, servings=2, tags=["반찬", "10분 요리", "다이어트"], allergens=[]),
    Recipe("fake-egg-roll", "계란말이", [I("달걀", 3, "개"), I("대파", 0.3, "대"), I("당근", 0.2, "개", optional=True), I("소금", 0.3, "작은술")],
           "1. 달걀을 풀고 잘게 썬 대파·당근, 소금을 섞는다.\n2. 약불 팬에 얇게 부어 익으면 돌돌 만다. 2~3번 반복한다.",
           cook_minutes=10, servings=2, tags=["반찬", "10분 요리", "고단백"], allergens=["달걀"]),
    Recipe("fake-kimchi-fried-rice", "김치볶음밥", [I("김치", 150, "g"), I("즉석밥", 1, "개"), I("달걀", 1, "개", optional=True), I("대파", 0.3, "대"), I("참기름", 1, "큰술")],
           "1. 대파를 볶아 파기름을 내고 김치를 넣어 3분 볶는다.\n2. 밥을 넣고 고루 볶은 뒤 참기름을 두른다.\n3. 달걀 프라이를 올린다.",
           cook_minutes=15, servings=1, tags=["한그릇", "매운맛"], allergens=["달걀"]),
    Recipe("fake-milk-french-toast", "우유 프렌치토스트", [I("식빵", 2, "장"), I("우유", 100, "ml"), I("달걀", 1, "개"), I("버터", 10, "g")],
           "1. 우유와 달걀을 섞어 식빵을 적신다.\n2. 버터 두른 팬에 앞뒤로 노릇하게 굽는다.",
           cook_minutes=10, servings=1, tags=["아침", "10분 요리"], allergens=["우유", "달걀", "밀"]),
]

_BY_ID = {r.id: r for r in SAMPLE_RECIPES}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _contains_allergen(recipe: Recipe, allergies: list[str]) -> bool:
    keys = {_norm(a) for a in allergies}
    names = {_norm(x) for x in recipe.allergens} | {_norm(i.name) for i in recipe.ingredients}
    return any(k and any(k in n for n in names) for k in keys)


def rank_recipes(
    recipes: list[Recipe],
    ingredients: list[str],
    in_stock: list[str],
    allergies: list[str],
    max_minutes: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> list[RecipeMatch]:
    """순수 함수: 알레르기 제외 → 시간 제한 → 점수(임박 재료 ×3 + 보유 비율 ×2 + 태그)."""
    wanted = {_norm(x) for x in ingredients}
    stock = {_norm(x) for x in in_stock}
    out: list[RecipeMatch] = []
    for r in recipes:
        if _contains_allergen(r, allergies):
            continue
        if max_minutes and r.cook_minutes and r.cook_minutes > max_minutes:
            continue
        names = [i.name for i in r.ingredients]
        uses = [n for n in names if _norm(n) in wanted]
        required = [i.name for i in r.ingredients if not i.optional]
        missing = [n for n in required if _norm(n) not in stock and _norm(n) not in wanted]
        have_ratio = 1 - len(missing) / max(len(required), 1)
        tag_bonus = len(set(tags or []) & set(r.tags))
        score = len(uses) * 3 + have_ratio * 2 + tag_bonus
        if uses or not wanted:
            out.append(RecipeMatch(recipe=r, score=round(score, 2), uses_expiring=uses, missing=missing))
    return sorted(out, key=lambda m: m.score, reverse=True)


def search_recipes(
    user_id: str,
    ingredients: list[str],
    max_minutes: Optional[int] = None,
    servings: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> list[RecipeMatch]:
    from lib.inventory import get_inventory
    from lib.preferences import get_allergies

    in_stock = [i.name for i in get_inventory(user_id)]
    return rank_recipes(SAMPLE_RECIPES, ingredients, in_stock, get_allergies(user_id), max_minutes, tags)[:5]


def get_recipe(recipe_id: str) -> Optional[Recipe]:
    return _BY_ID.get(recipe_id)
