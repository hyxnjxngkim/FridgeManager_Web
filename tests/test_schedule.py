import pytest

from lib.meal_plan import recipe_from_json, recipe_to_json
from lib.models import Recipe, RecipeIngredient as I, ScheduleEvent
from lib.schedule import event_label, validate_event


def test_validate_event():
    assert validate_event("guests", " 집들이 ", 4) == ("guests", "집들이", 4)
    assert validate_event("busy", "", 7) == ("busy", None, None)  # 손님 아닐 땐 손님 수 무시
    with pytest.raises(ValueError):
        validate_event("guests", None, 0)
    with pytest.raises(ValueError):
        validate_event("party", None, None)


def test_event_label():
    from datetime import date
    assert event_label(ScheduleEvent("1", date(2026, 11, 30), "guests", "집들이", 4)) == "👥 손님 4명 · 집들이"


def test_recipe_json_roundtrip_keeps_ingredients_and_ignores_unknown_fields():
    r = Recipe("x", "두부조림", [I("두부", 1, "모"), I("파", optional=True)], "굽는다", 15, 2, ["반찬"], ["대두"])
    data = recipe_to_json(r)
    data["future_field"] = "B가 나중에 추가한 칸"
    assert recipe_from_json(data) == r
