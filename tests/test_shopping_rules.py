from datetime import date

from lib.models import CatalogItem, InventoryItem, Recipe, RecipeIngredient as I
from lib.shopping_rules import build_shopping_list

D = date(2026, 11, 30)
CATALOG = [CatalogItem(1, "두부", [], None, 5, "fridge"), CatalogItem(2, "달걀", ["계란"], None, 30, "fridge")]


def stock(name, qty, unit, cat=None):
    return InventoryItem(name, name, cat, qty, unit, D, D, "estimated", "active")


def test_sums_same_ingredient_with_alias_and_conversion():
    r1 = Recipe("a", "계란말이", [I("달걀", 3, "개"), I("우유", 100, "ml")], "")
    r2 = Recipe("b", "프렌치토스트", [I("계란", 2, "개"), I("우유", 0.2, "L")], "")
    out = {n.name: n for n in build_shopping_list([(r1, None), (r2, None)], [], CATALOG)}
    assert out["달걀"].quantity == 5 and out["달걀"].recipes == ["계란말이", "프렌치토스트"]
    assert out["우유"].quantity == 300 and out["우유"].unit == "ml"


def test_subtracts_stock_and_skips_enough_or_incomparable():
    r = Recipe("a", "x", [I("달걀", 5, "개"), I("두부", 300, "g"), I("우유", 500, "ml")], "")
    inv = [stock("계란", 2, "개", 2), stock("두부", 1, "모", 1), stock("우유", 1, "L")]
    out = {n.name: n.quantity for n in build_shopping_list([(r, None)], inv, CATALOG)}
    assert out == {"달걀": 3}  # 두부는 단위가 달라 '있음', 우유는 1L로 충분


def test_scales_servings_and_ignores_optional_and_water():
    r = Recipe("a", "국", [I("두부", 100, "g"), I("물", 500, "ml"), I("파", 1, "대", optional=True)], "", servings=1)
    out = build_shopping_list([(r, 3)], [], CATALOG)
    assert [(n.name, n.quantity) for n in out] == [("두부", 300)]
