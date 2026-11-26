"""식단·장보기·달력 화면을 가짜 데이터로 실행 (AppTest)."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import lib.inventory as inv
import lib.meal_plan as mp
import lib.recipe_source as rs
import lib.schedule as sch
import lib.shopping as shop
from lib.models import AppUser, InventoryItem, Recipe, RecipeIngredient as I, RecipeMatch, ShoppingItem

ROOT = Path(__file__).resolve().parent.parent
USER = AppUser("user-1", "a@example.com")
TODAY = date(2026, 11, 26)
TOFU = InventoryItem("t1", "두부", 1, 1, "모", TODAY, date(2026, 11, 27), "estimated", "active")
RECIPE = Recipe("r1", "두부조림", [I("두부", 1, "모"), I("대파", 1, "대")], "굽는다", 15, 2)


@pytest.fixture
def db(monkeypatch):
    store = {"plans": [], "shop": []}
    monkeypatch.setattr("lib.dates.today_kst", lambda now=None: TODAY)
    monkeypatch.setattr(sch, "get_events", lambda uid, s, e: [])
    monkeypatch.setattr(inv, "get_expiring", lambda uid, days, include_expired=False: [TOFU])
    monkeypatch.setattr(inv, "get_inventory", lambda uid: [TOFU])
    monkeypatch.setattr(inv, "get_catalog", lambda: [])
    monkeypatch.setattr(rs, "search_recipes", lambda uid, names, **kw: [RecipeMatch(RECIPE, 3, ["두부"], [])])

    def save_week(uid, start, meals, days=7):
        store["plans"] = [mp.SavedMeal(m.day, m.match.recipe, m.servings, m.reason) for m in meals if m.match]

    monkeypatch.setattr(mp, "save_week", save_week)
    monkeypatch.setattr(mp, "get_week", lambda uid, start, days=7: list(store["plans"]))
    monkeypatch.setattr(mp, "get_plans_between", lambda uid, s, e: [(m.day, m.recipe.title) for m in store["plans"]])

    def replace(uid, needs):
        store["shop"] = [ShoppingItem(f"s{i}", n.name, n.quantity, n.unit, False, "plan", ", ".join(n.recipes)) for i, n in enumerate(needs)]

    monkeypatch.setattr(shop, "replace_plan_items", replace)
    monkeypatch.setattr(shop, "get_items", lambda uid: list(store["shop"]))
    return store


def run(page):
    at = AppTest.from_file(str(ROOT / "views" / page), default_timeout=60)
    at.session_state["user"] = USER
    at.run()
    assert not at.exception, at.exception
    return at


def test_make_plan_then_shopping_list(db):
    at = run("plan.py")
    assert "아직 식단이 없어요" in at.info[0].value
    next(b for b in at.button if "식단 짜기" in b.label).click().run()
    assert len(db["plans"]) == 7  # 레시피가 하나뿐이면 반복해서 7일을 채워요
    assert "반복" in db["plans"][1].reason
    assert any("두부조림" in m.value for m in at.markdown)

    next(b for b in at.button if "장보기 목록 만들기" in b.label).click().run()
    # 7일 × (두부 1모, 대파 1대) − 재고 두부 1모
    assert [(s.name, s.quantity) for s in db["shop"]] == [("대파", 7), ("두부", 6)]
    assert any("대파" in c.label for c in at.checkbox)


def test_calendar_page_renders(db):
    at = run("calendar.py")
    assert at.title[0].value == "달력"
    assert any("11/26(목)" in s.value for s in at.subheader)
    assert not any("두부 유통기한" in m.value for m in at.markdown)  # 두부는 27일이라 오늘(26일) 칸엔 없음
