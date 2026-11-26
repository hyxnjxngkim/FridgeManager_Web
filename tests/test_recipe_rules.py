"""레시피 점수 규칙 검사 (순수 함수)."""
from lib.recipe_rules import (
    BUSY_MAX_MINUTES,
    canonical,
    has_allergen,
    is_pantry,
    rank,
    same_ingredient,
    score_recipe,
)
from tests.recipe_fixtures import CATALOG, CUCUMBER_SALAD, DOENJANG_SOUP, SAMPLE_RECIPES, STEAMED_EGG


def test_busy_limit_is_15_minutes():
    assert BUSY_MAX_MINUTES == 15


# ── 재료 이름 맞추기 ────────────────────────────────
def test_catalog_aliases():
    assert canonical("파", CATALOG) == "대파"
    assert canonical("계란", CATALOG) == "달걀"
    assert canonical("다진 마늘", CATALOG) == "다진마늘"
    assert canonical("오이 ", CATALOG) == "오이"  # 카탈로그에 없으면 띄어쓰기만 정리


def test_same_ingredient_matches_endings_only():
    assert same_ingredient("두부", "연두부")
    assert same_ingredient("두부", "순두부")
    assert same_ingredient("새우", "칵테일새우")
    assert same_ingredient("파", "다진대파", CATALOG)  # '파' → '대파'
    assert same_ingredient("계란", "달걀", CATALOG)
    assert not same_ingredient("고추", "고추장")
    assert not same_ingredient("파", "파프리카", CATALOG)
    assert not same_ingredient("파", "양파", CATALOG)  # '파'는 대파로 바뀌어서 양파와 다름
    assert not same_ingredient("배", "양배추")  # 한 글자는 정확히 같을 때만


def test_pantry():
    assert is_pantry("소금") and is_pantry("물") and is_pantry("다진 마늘", CATALOG)
    assert not is_pantry("두부")


# ── 점수 ────────────────────────────────────────────
def test_score_counts_expiring_have_ratio_and_tags():
    m = score_recipe(DOENJANG_SOUP, expiring=["두부", "대파"], have=["감자"], wanted_tags=["끓이기"], catalog=CATALOG)
    assert m.uses_expiring == ["두부", "대파"]
    # 필수 재료(물 제외) 6개 중 두부·대파·감자 3개 보유 → 0.5
    assert m.missing == ["애느타리버섯", "양파", "된장"]
    assert m.score == 2 * 3 + 0.5 * 2 + 1


def test_optional_and_pantry_ingredients_are_not_missing():
    m = score_recipe(STEAMED_EGG, expiring=[], have=["연두부", "새우", "달걀", "생크림", "버터"], catalog=CATALOG)
    assert m.missing == []  # 설탕은 양념, 시금치는 고명(선택)
    assert m.score == 2.0  # 보유 비율 1.0 × 2


def test_rank_orders_by_score_then_expiring_then_missing():
    matches = [score_recipe(r, ["두부"], [], catalog=CATALOG) for r in SAMPLE_RECIPES]
    ranked = rank(matches)
    assert [m.recipe.title for m in ranked][0] == "순두부 사과 소스 오이무침"  # 없는 재료가 가장 적음
    assert all(m.uses_expiring == ["두부"] for m in ranked)


def test_has_allergen():
    assert has_allergen(CUCUMBER_SALAD, ["땅콩"])
    assert not has_allergen(DOENJANG_SOUP, ["땅콩", "새우"])
