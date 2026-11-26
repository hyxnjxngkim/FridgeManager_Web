"""가짜 search_recipes() 와 recipe_card() 검사 (DB 없이)."""
from streamlit.testing.v1 import AppTest

from lib.models import Recipe, RecipeIngredient, RecipeMatch
from lib.recipes import search_recipes

USER_ID = "user-1"


# ── search_recipes(): 모양 ─────────────────────────────
def test_returns_recipe_matches_with_shared_shape():
    results = search_recipes(USER_ID, ["두부"])
    assert results, "레시피가 하나 이상 나와야 해요"
    for m in results:
        assert isinstance(m, RecipeMatch)
        assert isinstance(m.recipe, Recipe)
        assert all(isinstance(i, RecipeIngredient) for i in m.recipe.ingredients)
        assert isinstance(m.score, float)
        assert m.recipe.image_url is None or m.recipe.image_url.startswith("https://")


def test_optional_arguments_can_be_omitted_or_given():
    assert search_recipes(USER_ID, [])  # 재료가 없어도 오류 없이 돌려줌
    assert search_recipes(USER_ID, ["두부"], max_minutes=None, servings=2, tags=["반찬"]) is not None


# ── search_recipes(): 가짜 버전의 동작 ─────────────────
def test_recipes_using_more_expiring_ingredients_come_first():
    results = search_recipes(USER_ID, ["두부", "대파"])
    top = results[0]
    assert top.recipe.title == "된장국"  # 두부 + 대파 둘 다 씀
    assert top.uses_expiring == ["두부", "대파"]
    assert top.score == 6.0


def test_partial_name_matches_like_tofu_variants():
    titles = {m.recipe.title: m for m in search_recipes(USER_ID, ["두부"])}
    # '두부' 는 연두부·두부·순두부 모두와 맞아요
    assert all(m.uses_expiring == ["두부"] for m in titles.values())


def test_max_minutes_filters_out_longer_recipes():
    results = search_recipes(USER_ID, ["두부"], max_minutes=10)
    assert [m.recipe.title for m in results] == ["순두부 사과 소스 오이무침"]


def test_tags_add_score_but_do_not_filter():
    base = {m.recipe.title: m.score for m in search_recipes(USER_ID, [])}
    tagged = {m.recipe.title: m.score for m in search_recipes(USER_ID, [], tags=["국&찌개"])}
    assert set(base) == set(tagged)  # 아무것도 빠지지 않음
    assert tagged["된장국"] == base["된장국"] + 1


def test_no_missing_in_fake_version():
    assert all(m.missing == [] for m in search_recipes(USER_ID, ["사과"]))


# ── recipe_card() ─────────────────────────────────────
def _card_script():
    from lib.recipes import search_recipes
    from lib.ui import recipe_card

    match = next(m for m in search_recipes("user-1", ["두부"]) if m.recipe.title == "새우 두부 계란찜")
    recipe_card(match)


def test_recipe_card_shows_info_without_buttons():
    at = AppTest.from_function(_card_script, default_timeout=60)
    at.run()
    assert not at.exception, at.exception

    texts = " ".join(md.value for md in at.markdown) + " " + " ".join(c.value for c in at.caption)
    assert "새우 두부 계란찜" in texts
    assert "구출 재료: `두부`" in texts
    assert "연두부 75g" in texts
    assert "시금치 10g(선택)" in texts
    assert "약 20분 (추정)" in texts
    assert "알레르기 성분: 달걀, 우유, 대두, 새우" in texts
    assert at.expander[0].label == "만드는 법"
    assert not at.button  # 버튼은 카드에 넣지 않아요
