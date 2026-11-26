"""테스트용 레시피 3개 — 식품안전나라 COOKRCP01 에서 옮김 (DB 없이 쓰는 가짜 데이터)."""
from lib.models import CatalogItem, Recipe, RecipeIngredient

_IMG = "https://www.foodsafetykorea.go.kr/uploadimg/cook/10_{seq:05d}_2.png"

STEAMED_EGG = Recipe(
    id="r-28",
    title="새우 두부 계란찜",
    ingredients=[
        RecipeIngredient("연두부", 75, "g"),
        RecipeIngredient("칵테일새우", 20, "g"),
        RecipeIngredient("달걀", 30, "g"),
        RecipeIngredient("생크림", 13, "g"),
        RecipeIngredient("설탕", 5, "g"),
        RecipeIngredient("무염버터", 5, "g"),
        RecipeIngredient("시금치", 10, "g", optional=True),
    ],
    steps="1. 손질된 새우를 끓는 물에 데쳐 건진다.\n2. 재료를 믹서에 갈아 그릇에 담는다.\n3. 찜기에 10분 정도 찐다.",
    cook_minutes=20,
    servings=1,
    tags=["반찬", "찌기", "연두부"],
    allergens=["달걀", "우유", "대두", "새우"],
    image_url=_IMG.format(seq=28),
)

DOENJANG_SOUP = Recipe(
    id="r-37",
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
    steps="1. 채소를 썬다.\n2. 된장을 풀어 끓인다.\n3. 대파를 넣어 마무리한다.",
    cook_minutes=15,
    servings=1,
    tags=["국&찌개", "끓이기"],
    allergens=["대두"],
    image_url=_IMG.format(seq=37),
)

CUCUMBER_SALAD = Recipe(
    id="r-32",
    title="순두부 사과 소스 오이무침",
    ingredients=[
        RecipeIngredient("오이", 70, "g"),
        RecipeIngredient("다진 땅콩", 10, "g"),
        RecipeIngredient("순두부", 40, "g"),
        RecipeIngredient("사과", 50, "g"),
    ],
    steps="1. 사과, 순두부를 갈아 소스를 만든다.\n2. 오이를 썬다.\n3. 버무리고 땅콩을 뿌린다.",
    cook_minutes=10,
    servings=1,
    tags=["반찬", "기타", "순두부", "다이어트"],
    allergens=["땅콩", "대두"],
    image_url=_IMG.format(seq=32),
)

SAMPLE_RECIPES = [STEAMED_EGG, DOENJANG_SOUP, CUCUMBER_SALAD]

CATALOG = [
    CatalogItem(1, "두부", [], "달걀·두부", 5, "fridge"),
    CatalogItem(2, "대파", ["파"], "채소", 10, "fridge"),
    CatalogItem(3, "달걀", ["계란"], "달걀·두부", 21, "fridge"),
    CatalogItem(4, "다진마늘", ["다진 마늘"], "채소", 7, "fridge"),
]
