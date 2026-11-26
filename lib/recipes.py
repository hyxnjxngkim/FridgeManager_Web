"""레시피 검색 (Phase 3, 팀원 B).

⚠️ 지금은 **가짜 버전**이에요 (PLAN.md 11-2).
   - DB·임베딩 없이, 식품안전나라 레시피 3개를 고정 데이터로 들고 있어요.
   - 함수 모양(입력·출력)은 진짜 버전과 같아요. A(Phase 4)는 이 모양 그대로 가져다 쓰면 돼요.
   - 진짜 버전(벡터 검색 → 알레르기 SQL 제외 → 코드 점수화)으로 바뀌어도 모양은 바꾸지 않아요.
     바꿔야 하면 먼저 A에게 알려요.
"""
from __future__ import annotations

from typing import Optional

from lib.models import Recipe, RecipeIngredient, RecipeMatch

# 점수 가중치 (PLAN 5장 ③: 임박 재료 사용 수 × 3 + … + 취향 태그 일치)
EXPIRING_WEIGHT = 3
TAG_WEIGHT = 1

# ── 가짜 데이터: 식품안전나라 조리식품의 레시피 DB(COOKRCP01)에서 옮긴 3개 ──
# cook_minutes 는 추정값, servings 는 1인분 (변환 규칙 참고)
_IMG = "https://www.foodsafetykorea.go.kr/uploadimg/cook/10_{seq:05d}_2.png"

_FAKE_RECIPES: list[Recipe] = [
    Recipe(
        id="fake-28",
        title="새우 두부 계란찜",
        ingredients=[
            RecipeIngredient("연두부", 75, "g"),
            RecipeIngredient("칵테일새우", 20, "g"),
            RecipeIngredient("달걀", 30, "g"),
            RecipeIngredient("생크림", 13, "g"),
            RecipeIngredient("설탕", 5, "g"),
            RecipeIngredient("무염버터", 5, "g"),
            RecipeIngredient("시금치", 10, "g", optional=True),  # 고명
        ],
        steps=(
            "1. 손질된 새우를 끓는 물에 데쳐 건진다.\n"
            "2. 연두부, 달걀, 생크림, 설탕에 녹인 무염버터를 믹서에 넣고 간 뒤 새우를 함께 섞어 그릇에 담는다.\n"
            "3. 시금치를 잘게 다져 그릇에 뿌리고 찜기에 넣고 중간 불에서 10분 정도 찐다."
        ),
        cook_minutes=20,
        servings=1,
        tags=["반찬", "찌기", "연두부"],
        allergens=["갑각류", "대두", "알류", "우유"],
        image_url=_IMG.format(seq=28),
    ),
    Recipe(
        id="fake-37",
        title="된장국",
        ingredients=[
            RecipeIngredient("두부", 20, "g"),
            RecipeIngredient("애느타리버섯", 20, "g"),
            RecipeIngredient("감자", 10, "g"),
            RecipeIngredient("양파", 10, "g"),
            RecipeIngredient("대파", 10, "g"),
            RecipeIngredient("된장", 5, "g"),
            RecipeIngredient("물", 300, "ml"),
        ],
        steps=(
            "1. 감자, 양파는 얇게 썰고 애느타리버섯은 썰어 달궈진 팬에 굽는다.\n"
            "2. 냄비에 물을 붓고 된장을 푼 뒤 감자, 양파, 두부를 넣어 끓인 후 건더기를 믹서에 갈아 다시 넣고 한 번 더 끓인다.\n"
            "3. 구운 애느타리버섯과 대파를 넣어 끓인 후 그릇에 담는다."
        ),
        cook_minutes=15,
        servings=1,
        tags=["국&찌개", "끓이기"],
        allergens=["대두"],
        image_url=_IMG.format(seq=37),
    ),
    Recipe(
        id="fake-32",
        title="순두부 사과 소스 오이무침",
        ingredients=[
            RecipeIngredient("오이", 70, "g"),
            RecipeIngredient("땅콩", 10, "g"),
            RecipeIngredient("순두부", 40, "g"),
            RecipeIngredient("사과", 50, "g"),
        ],
        steps=(
            "1. 사과, 순두부를 믹서에 넣고 곱게 갈아 소스를 만든다.\n"
            "2. 오이는 소금으로 문질러 씻어 반을 갈라 씨를 제거하고 어슷썰기를 한다.\n"
            "3. 썰어 놓은 오이에 순두부사과 소스를 넣고 버무린 후 다진 땅콩을 뿌려 마무리한다."
        ),
        cook_minutes=10,
        servings=1,
        tags=["반찬", "기타", "순두부"],
        allergens=["땅콩", "대두"],
        image_url=_IMG.format(seq=32),
    ),
]


def _same_ingredient(a: str, b: str) -> bool:
    """가짜 버전의 간단한 이름 맞추기: 한쪽 이름이 다른 쪽에 들어 있으면 같은 재료.
    (예: '두부' ↔ '연두부'. 진짜 버전은 카탈로그 별칭으로 맞춰요)"""
    a, b = a.strip(), b.strip()
    return bool(a and b) and (a in b or b in a)


def search_recipes(
    user_id: str,
    ingredients: list[str],
    max_minutes: Optional[int] = None,
    servings: Optional[int] = None,
    tags: Optional[list[str]] = None,
) -> list[RecipeMatch]:
    """임박 재료(ingredients)를 많이 쓰는 레시피부터 돌려줘요.

    - user_id: 알레르기 제외에 쓸 자리 (가짜 버전은 받기만 해요)
    - ingredients: 임박 재료 이름 목록, 예: ["두부", "우유"]
    - max_minutes: 주어지면 조리 시간이 이보다 긴 레시피는 빼요
    - servings: 몇 인분인지 (가짜 버전은 받기만 해요)
    - tags: 일치하는 태그마다 점수 +1 (거르지는 않아요)

    점수 = 임박 재료 사용 수 × 3 + 태그 일치 수 × 1. 점수가 높은 순, 같으면 제목 순.
    가짜 버전의 missing 은 항상 빈 목록이에요 (재고 전체를 보지 않기 때문).
    """
    wanted_tags = set(tags or [])
    matches: list[RecipeMatch] = []
    for recipe in _FAKE_RECIPES:
        if max_minutes is not None and recipe.cook_minutes is not None and recipe.cook_minutes > max_minutes:
            continue
        uses = [
            name
            for name in ingredients
            if any(_same_ingredient(name, ing.name) for ing in recipe.ingredients)
        ]
        tag_hits = len(wanted_tags & set(recipe.tags))
        score = float(len(uses) * EXPIRING_WEIGHT + tag_hits * TAG_WEIGHT)
        matches.append(RecipeMatch(recipe=recipe, score=score, uses_expiring=uses, missing=[]))

    matches.sort(key=lambda m: (-m.score, m.recipe.title))
    return matches
