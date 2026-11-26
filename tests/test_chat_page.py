"""채팅·설정 화면을 가짜 데이터로 실행 (AppTest)."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import lib.agent as agent
import lib.cooking as cooking
import lib.inventory as inv
import lib.llm as llm
import lib.preferences as prefs
import lib.recipe_source as rs
from lib.models import Recipe, RecipeIngredient, AppUser, InventoryItem, Preference, RecipeMatch

ROOT = Path(__file__).resolve().parent.parent
USER = AppUser("user-1", "a@example.com")
TODAY = date(2026, 11, 26)
TOFU_RECIPE = Recipe("r-tofu", "두부조림", [RecipeIngredient("두부", 1, "모"), RecipeIngredient("대파", 0.5, "대")], "1. 굽는다.\n2. 졸인다.", cook_minutes=15, servings=2, allergens=["대두"])
SAMPLE_RECIPES = [TOFU_RECIPE]
TOFU = InventoryItem("t1", "두부", 1, 2, "모", TODAY, date(2026, 11, 27), "estimated", "active")


@pytest.fixture
def env(monkeypatch):
    applied = []
    monkeypatch.setattr(llm, "llm_unavailable_reason", lambda: "AWS 자격증명이 없어요.")
    monkeypatch.setattr(inv, "get_expiring", lambda uid, days, include_expired=False: [TOFU])
    monkeypatch.setattr(inv, "get_inventory", lambda uid: [TOFU])
    monkeypatch.setattr(inv, "get_catalog", lambda: [])
    monkeypatch.setattr(rs, "search_recipes", lambda uid, ing, **kw: [RecipeMatch(SAMPLE_RECIPES[0], 3, ["두부"], [])])
    monkeypatch.setattr(cooking, "apply_cook", lambda uid, plan: applied.append((uid, plan)) or 1)
    monkeypatch.setattr("lib.dates.today_kst", lambda now=None: TODAY)
    return applied


def run(page):
    at = AppTest.from_file(str(ROOT / "views" / page), default_timeout=60)
    at.session_state["user"] = USER
    at.run()
    assert not at.exception, at.exception
    return at


def test_chat_without_llm_quick_recommend_and_cook(env):
    at = run("chat.py")
    assert "Claude 와 대화할 수 없어요" in at.warning[0].value
    assert at.chat_input[0].disabled

    at.button(key=next(b.key for b in at.button if "임박 재료로" in b.label)).click().run()
    assert any("두부조림" in m.value for m in at.markdown)

    cook_btn = next(b for b in at.button if "이거 만들게" in b.label)
    cook_btn.click().run()
    assert any("재고 빼기 확인" in h.value for h in at.subheader)

    next(b for b in at.button if "확정" in b.label).click().run()
    assert not at.exception
    uid, plan = env[0]
    assert uid == USER.id and plan.lines[0].amount == 1  # 두부 1모
    assert any("구출했어요" in m.value for m in at.markdown)


def test_settings_lists_and_deletes(monkeypatch):
    store = [Preference("p1", "allergy", "땅콩"), Preference("p2", "like", "매운맛")]
    monkeypatch.setattr(prefs, "get_preferences", lambda uid: list(store))
    monkeypatch.setattr(prefs, "delete_preference_by_id", lambda uid, pid: store.remove(next(p for p in store if p.id == pid)))
    at = run("settings.py")
    assert any("땅콩" in m.value for m in at.markdown)
    at.button(key="del-p1").click().run()
    assert [p.id for p in store] == ["p2"]
