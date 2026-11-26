from datetime import date

import pytest

from lib.catalog import match_catalog
from lib.inventory_rules import ItemInput, expiry_for_new, expiry_for_update, validate
from lib.models import CatalogItem

CATALOG = [
    CatalogItem(1, "두부", ["부침두부"], "달걀·두부", 5, "fridge"),
    CatalogItem(2, "대파", ["파"], "채소", 10, "fridge"),
    CatalogItem(3, "달걀", ["계란"], "달걀·두부", 30, "fridge"),
]
TODAY = date(2026, 11, 26)


def test_match_by_name_alias_and_spaces():
    assert match_catalog("두부", CATALOG).id == 1
    assert match_catalog("계란", CATALOG).id == 3
    assert match_catalog(" 부침 두부 ", CATALOG).id == 1
    assert match_catalog("치즈", CATALOG) is None
    assert match_catalog("", CATALOG) is None


def test_validate_trims_and_rejects_bad_input():
    item = validate(ItemInput("  두부 ", 2, " 모 ", TODAY))
    assert (item.name, item.unit) == ("두부", "모")
    with pytest.raises(ValueError):
        validate(ItemInput("", 1, None, TODAY))
    with pytest.raises(ValueError):
        validate(ItemInput("두부", 0, None, TODAY))
    with pytest.raises(ValueError):
        validate(ItemInput("가" * 51, 1, None, TODAY))


def test_new_item_uses_manual_date_then_catalog_estimate():
    assert expiry_for_new(ItemInput("두부", 1, None, TODAY, date(2026, 12, 3)), CATALOG)[:2] == (
        date(2026, 12, 3), "manual",
    )
    assert expiry_for_new(ItemInput("파", 1, None, TODAY), CATALOG)[:2] == (
        date(2026, 12, 6), "estimated",
    )


def test_new_unknown_item_requires_date():
    with pytest.raises(ValueError, match="유통기한을 직접"):
        expiry_for_new(ItemInput("치즈", 1, None, TODAY), CATALOG)


def test_update_reestimates_when_only_purchase_date_changes():
    original_expires = date(2026, 12, 1)  # 11-26 + 5일
    changed = ItemInput("두부", 1, None, date(2026, 11, 28), original_expires)
    assert expiry_for_update(changed, TODAY, original_expires, "estimated", CATALOG)[:2] == (
        date(2026, 12, 3), "estimated",
    )


def test_update_marks_manual_when_expiry_edited():
    changed = ItemInput("두부", 1, None, TODAY, date(2026, 12, 10))
    assert expiry_for_update(changed, TODAY, date(2026, 12, 1), "estimated", CATALOG)[:2] == (
        date(2026, 12, 10), "manual",
    )


def test_update_keeps_manual_date_when_purchase_changes():
    changed = ItemInput("두부", 1, None, date(2026, 11, 28), date(2026, 12, 10))
    assert expiry_for_update(changed, TODAY, date(2026, 12, 10), "manual", CATALOG)[:2] == (
        date(2026, 12, 10), "manual",
    )
