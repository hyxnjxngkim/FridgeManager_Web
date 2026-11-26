"""알레르기 이중 안전장치 (lib/recipe_source.py)."""
import lib.preferences as prefs
import lib.recipes as b_recipes
from lib.models import Recipe, RecipeIngredient as I, RecipeMatch
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


def test_peanut_recipe_from_b_is_removed_for_peanut_allergy(monkeypatch):
    """B의 가짜 검색은 알레르기를 안 거르므로, 연결점에서 걸러져야 해요."""
    monkeypatch.setattr(prefs, "get_allergies", lambda uid: ["땅콩"])
    titles = [m.recipe.title for m in search_recipes("u1", ["오이", "두부"])]
    assert titles  # 다른 레시피는 남아요
    assert all("땅콩" not in m.recipe.allergens for m in search_recipes("u1", ["오이"]))
    raw = [m.recipe.title for m in b_recipes.search_recipes("u1", ["오이"])]
    assert any(t not in titles for t in raw)  # 실제로 하나 이상 빠졌어요


def test_no_allergies_passes_everything(monkeypatch):
    monkeypatch.setattr(prefs, "get_allergies", lambda uid: [])
    assert len(search_recipes("u1", ["두부"])) == len(b_recipes.search_recipes("u1", ["두부"]))
