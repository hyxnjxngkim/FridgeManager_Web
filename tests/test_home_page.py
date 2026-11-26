"""홈 화면 (구출 레시피 카드) — DB 없이 가짜 함수로."""
from datetime import date
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import lib.inventory as inv
import lib.recipes as rec
from lib.models import AppUser, InventoryItem
from lib.recipe_rules import score_recipe
from tests.recipe_fixtures import SAMPLE_RECIPES

TODAY = date(2026, 11, 26)
USER = AppUser("user-1", "a@example.com")
PAGE = str(Path(__file__).resolve().parent.parent / "views" / "home.py")

TOFU = InventoryItem("a", "두부", 1, 1, "모", TODAY, date(2026, 11, 27), "estimated", "active")
OLD_MILK = InventoryItem("b", "우유", None, 1, "팩", TODAY, date(2026, 11, 24), "estimated", "active")


@pytest.fixture
def page(monkeypatch):
    state = {"expiring": [TOFU, OLD_MILK], "search": None, "calls": []}

    def fake_search(user_id, ingredients, max_minutes=None, servings=None, tags=None):
        state["calls"].append((user_id, ingredients))
        if state["search"] == "error":
            raise RuntimeError("db down")
        return [score_recipe(r, ingredients, []) for r in SAMPLE_RECIPES] if state["search"] is None else state["search"]

    monkeypatch.setattr(inv, "get_expiring", lambda user_id, days, include_expired=False: state["expiring"])
    monkeypatch.setattr(rec, "search_recipes", fake_search)
    monkeypatch.setattr("lib.dates.today_kst", lambda now=None: TODAY)
    # st.page_link 는 st.navigation 안에서만 동작해서, 홈 파일만 따로 돌릴 땐 빈 함수로 바꿔요
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    return state


def run():
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["user"] = USER
    at.run()
    assert not at.exception, at.exception
    return at


def _texts(at):
    return " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)


def test_shows_three_recipe_cards_for_rescue_items(page):
    at = run()
    assert page["calls"] == [("user-1", ["두부"])]  # 지난 우유는 빼고 임박 재료만
    texts = _texts(at)
    assert all(r.title in texts for r in SAMPLE_RECIPES)
    assert "레시피 데이터: 식품안전나라" in texts


def test_no_rescue_items_means_no_search(page):
    page["expiring"] = []
    at = run()
    assert page["calls"] == []
    assert "임박한 재료가 생기면" in _texts(at)


def test_no_results_and_errors_do_not_break_the_page(page):
    page["search"] = []
    assert "찾지 못했어요" in run().info[0].value
    page["search"] = "error"
    assert "불러오지 못했어요" in run().warning[-1].value
