from datetime import date

from lib.cooking_rules import plan_cook, summarize_plan
from lib.models import CatalogItem, InventoryItem, Recipe, RecipeIngredient as I

TODAY = date(2026, 11, 26)
CATALOG = [
    CatalogItem(1, "두부", ["부침두부"], "달걀·두부", 5, "fridge"),
    CatalogItem(2, "대파", ["파"], "채소", 10, "fridge"),
    CatalogItem(3, "콩나물", [], "채소", 3, "fridge"),
    CatalogItem(4, "간장", ["진간장"], "양념", 365, "room"),
    CatalogItem(5, "우유", [], "유제품", 7, "fridge"),
]


def item(id, name, qty, unit, expires, cat=None):
    return InventoryItem(id, name, cat, qty, unit, TODAY, expires, "estimated", "active")


def test_fefo_same_unit_splits_across_items_oldest_first():
    inv = [
        item("new", "콩나물", 300, "g", date(2026, 11, 30), 3),
        item("old", "콩나물", 150, "g", date(2026, 11, 27), 3),
    ]
    plan = plan_cook(Recipe("r", "콩나물국", [I("콩나물", 200, "g")], ""), inv, CATALOG, TODAY)
    assert [(ln.item_id, ln.amount) for ln in plan.lines] == [("old", 150), ("new", 50)]
    assert plan.rescued_count() == 1  # old 만 D-1
    assert plan.missing == []


def test_scales_by_servings():
    inv = [item("m", "우유", 1000, "ml", date(2026, 12, 1), 5)]
    recipe = Recipe("r", "라떼", [I("우유", 200, "ml")], "", servings=1)
    assert plan_cook(recipe, inv, CATALOG, TODAY, servings=3).lines[0].amount == 600


def test_count_unit_mismatch_suggests_one():
    inv = [item("t", "두부", 2, "모", date(2026, 11, 28), 1)]
    plan = plan_cook(Recipe("r", "두부조림", [I("두부", 300, "g")], ""), inv, CATALOG, TODAY)
    ln = plan.lines[0]
    assert ln.amount == 1 and "1모" in ln.note


def test_alias_matches_and_non_count_mismatch_is_zero():
    inv = [item("p", "파", 500, "g", date(2026, 12, 3))]  # catalog_id 없음, 별칭으로 대파
    plan = plan_cook(Recipe("r", "x", [I("대파", 1, "대")], ""), inv, CATALOG, TODAY)
    assert plan.lines[0].item_id == "p" and plan.lines[0].amount == 0
    assert "직접 입력" in plan.lines[0].note


def test_seasoning_defaults_to_zero():
    inv = [item("s", "진간장", 1, "병", date(2027, 11, 1), 4)]
    plan = plan_cook(Recipe("r", "x", [I("간장", 3, "큰술")], ""), inv, CATALOG, TODAY)
    assert plan.lines[0].amount == 0


def test_missing_required_and_optional_ignored():
    recipe = Recipe("r", "x", [I("두부", 1, "모"), I("당근", 1, "개", optional=True)], "")
    plan = plan_cook(recipe, [], CATALOG, TODAY)
    assert plan.missing == ["두부"] and plan.lines == []


def test_expired_and_inactive_items():
    inv = [
        item("gone", "우유", 0, "ml", date(2026, 12, 1), 5),  # 수량 0은 제외
        item("exp", "우유", 500, "ml", date(2026, 11, 20), 5),  # 지난 것은 빼지만 구출 아님
    ]
    plan = plan_cook(Recipe("r", "x", [I("우유", 100, "ml")], ""), inv, CATALOG, TODAY)
    assert [ln.item_id for ln in plan.lines] == ["exp"]
    assert plan.rescued_count() == 0


def test_summary_mentions_confirmation():
    inv = [item("t", "두부", 1, "모", date(2026, 11, 27), 1)]
    text = summarize_plan(plan_cook(Recipe("r", "두부조림", [I("두부", 1, "모")], ""), inv, CATALOG, TODAY))
    assert "두부 1모" in text and "확인" in text


def test_converts_ml_to_l_and_g_to_kg():
    inv = [item("m", "우유", 1, "L", date(2026, 11, 27), 5)]
    ln = plan_cook(Recipe("r", "x", [I("우유", 100, "ml")], ""), inv, CATALOG, TODAY).lines[0]
    assert ln.amount == 0.1 and ln.note == ""
    inv = [item("k", "콩나물", 0.5, "kg", date(2026, 11, 27), 3)]
    ln = plan_cook(Recipe("r", "x", [I("콩나물", 200, "g")], ""), inv, CATALOG, TODAY).lines[0]
    assert ln.amount == 0.2


def test_convert_helper():
    from lib.cooking_rules import convert
    assert convert(1500, "g", "kg") == 1.5
    assert convert(2, "L", "ml") == 2000
    assert convert(1, "모", "g") is None
    assert convert(3, None, None) == 3
