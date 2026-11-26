from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import lib.feedback as fb
import lib.stats as stats
from lib.feedback import UnratedMeal
from lib.models import AppUser

ROOT = Path(__file__).resolve().parent.parent
USER = AppUser("user-1", "a@example.com")
TODAY = date(2026, 11, 26)


@pytest.fixture
def data(monkeypatch):
    rated = []
    meals = [
        {"day": date(2026, 11, 24), "rescued": 2, "title": "된장국", "rating": 1},
        {"day": date(2026, 11, 25), "rescued": 1, "title": "된장국", "rating": None},
        {"day": date(2026, 11, 26), "rescued": 0, "title": "계란찜", "rating": None},
    ]
    monkeypatch.setattr("lib.dates.today_kst", lambda now=None: TODAY)
    monkeypatch.setattr(stats, "meal_rows", lambda uid, since: meals)
    monkeypatch.setattr(stats, "discard_days", lambda uid, since: [date(2026, 11, 25)])
    monkeypatch.setattr(stats, "used_count", lambda uid, since: 4)
    monkeypatch.setattr(fb, "unrated_meals", lambda uid, days=14: [UnratedMeal("m3", "계란찜", TODAY)])
    fake = lambda uid, mid, r, c: rated.append((mid, r, c))
    monkeypatch.setattr(fb, "record_feedback", fake)
    monkeypatch.setattr("lib.feedback_ui.record_feedback", fake)  # 다른 테스트가 먼저 불러왔을 때 대비
    monkeypatch.setattr("lib.llm.llm_unavailable_reason", lambda: "없음")
    return rated


def test_dashboard_numbers_top_and_feedback(data):
    at = AppTest.from_file(str(ROOT / "views" / "dashboard.py"), default_timeout=60)
    at.session_state["user"] = USER
    at.run()
    assert not at.exception, at.exception
    values = {m.label: m.value for m in at.metric}
    assert values == {"구출한 재료": "3개", "버린 재료": "1개", "구출률": "75%"}
    assert any("1. **된장국** · 2번 · 👍 1" in m.value for m in at.markdown)

    assert at.radio(key="dash-period").value == "이번 달"
    feedback_radio = next(r for r in at.radio if "👎 별로였어요" in r.options)
    feedback_radio.set_value("👎 별로였어요")
    at.text_input[0].set_value("너무 싱거웠어요")
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert data == [("m3", -1, "너무 싱거웠어요")]


def test_period_switch(data):
    at = AppTest.from_file(str(ROOT / "views" / "dashboard.py"), default_timeout=60)
    at.session_state["user"] = USER
    at.run()
    at.radio(key="dash-period").set_value("전체").run()
    assert not at.exception, at.exception
