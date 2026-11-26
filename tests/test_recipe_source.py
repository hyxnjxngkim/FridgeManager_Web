"""알레르기 이중 안전장치 (lib/recipe_source.py)."""
import pytest

import lib.feedback as fb
import lib.preferences as prefs
import lib.recipes as b_recipes
from lib.models import Preference, Recipe, RecipeIngredient as I, RecipeMatch
from lib.recipe_source import allergy_terms, contains_allergen, search_recipes


def match(title, ingredients, allergens):
    return RecipeMatch(Recipe("x", title, [I(n) for n in ingredients], "", allergens=allergens), 1.0)


def test_alias_groups_cover_common_names():
    assert {"알류", "달걀"} <= allergy_terms(["계란"])
    assert "갑각류" in allergy_terms(["새우"])
    assert allergy_terms([" "]) == set()


def test_matches_by_allergen_label_or_ingredient_name():
    shrimp = match("새우 계란찜", ["칵테일새우", "달걀"], ["갑각류", "알류"])
    assert contains_allergen(shrimp, ["새우"])        # 재료 이름에 포함
    assert contains_allergen(shrimp, ["계란"])        # '알류' 표기와 같은 그룹
    assert contains_allergen(shrimp, ["갑각류"])
    assert not contains_allergen(shrimp, ["땅콩"])
    assert not contains_allergen(shrimp, [])


B_RESULTS = [
    match("순두부 사과 소스 오이무침", ["오이", "땅콩", "순두부"], ["땅콩", "대두"]),
    match("된장국", ["두부", "대파", "된장"], ["대두"]),
    match("오이냉국", ["오이", "식초"], []),
]


@pytest.fixture
def fake_b(monkeypatch):
    """B의 진짜 검색은 DB·Bedrock 을 쓰니 테스트에선 고정 결과로 바꿔요."""
    monkeypatch.setattr(b_recipes, "search_recipes", lambda uid, ing, **kw: list(B_RESULTS))


def test_peanut_recipe_from_b_is_removed_for_peanut_allergy(monkeypatch, fake_b):
    monkeypatch.setattr(prefs, "get_preferences", lambda uid: [Preference("p", "allergy", "땅콩")])
    titles = [m.recipe.title for m in search_recipes("u1", ["오이", "두부"])]
    assert titles == ["된장국", "오이냉국"]  # 땅콩 레시피만 빠지고 나머지는 남아요


def test_no_allergies_passes_everything(monkeypatch, fake_b):
    monkeypatch.setattr(prefs, "get_preferences", lambda uid: [])
    assert len(search_recipes("u1", ["두부"])) == len(B_RESULTS)


@pytest.fixture(autouse=True)
def no_history(monkeypatch):
    monkeypatch.setattr(fb, "recipe_history", lambda uid: {})
