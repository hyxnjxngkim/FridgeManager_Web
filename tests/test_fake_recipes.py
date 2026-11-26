from lib.fake_recipes import SAMPLE_RECIPES, rank_recipes


def titles(matches):
    return [m.recipe.title for m in matches]


def test_expiring_ingredient_ranks_first():
    out = rank_recipes(SAMPLE_RECIPES, ["콩나물"], in_stock=["콩나물", "대파"], allergies=[])
    assert titles(out)[0] == "콩나물국"
    assert out[0].uses_expiring == ["콩나물"]


def test_allergy_excludes_recipe_by_allergen_or_ingredient():
    out = rank_recipes(SAMPLE_RECIPES, ["달걀"], in_stock=["달걀"], allergies=["달걀"])
    assert "계란말이" not in titles(out)
    assert all("달걀" not in m.recipe.allergens for m in out)


def test_max_minutes_filter():
    out = rank_recipes(SAMPLE_RECIPES, ["두부", "대파"], in_stock=["두부"], allergies=[], max_minutes=10)
    assert "두부조림" not in titles(out)


def test_missing_lists_required_not_in_stock():
    out = rank_recipes(SAMPLE_RECIPES, ["시금치"], in_stock=["시금치"], allergies=[])
    spinach = next(m for m in out if m.recipe.title == "시금치나물")
    assert "참기름" in spinach.missing and "시금치" not in spinach.missing
