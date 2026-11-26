from types import SimpleNamespace as NS

import pytest

import lib.agent as agent
import lib.feedback as fb
from lib.agent import AgentState, run_tool
from lib.models import Preference


class FakeClient:
    def __init__(self, tool_input=None, error=None):
        self.calls = []
        self.messages = NS(create=self._create)
        self._input, self._error = tool_input, error

    def _create(self, **kw):
        self.calls.append(kw)
        if self._error:
            raise self._error
        return NS(content=[NS(type="tool_use", id="t", name="save_taste_changes", input=self._input)])


def test_parse_changes_validates():
    raw = {"changes": [{"kind": "dislike", "value": " 매운맛 "}, {"kind": "hate", "value": "x"},
                       {"kind": "like", "value": ""}, "junk", {"kind": "diet", "value": "가" * 31}]}
    assert fb.parse_changes(raw) == [("dislike", "매운맛")]
    assert fb.parse_changes("nope") == []


def test_learn_from_comment_bumps_preferences(monkeypatch):
    saved = []
    monkeypatch.setattr(fb, "bump_preference", lambda uid, k, v: saved.append((uid, k, v)) or Preference("p", k, v, 2))
    client = FakeClient({"changes": [{"kind": "dislike", "value": "매운맛"}]})
    out = fb.learn_from_comment(client, "u1", "떡볶이", -1, "너무 매웠어요")
    assert saved == [("u1", "dislike", "매운맛")] and out == ["싫어함: 매운맛"]
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "save_taste_changes"}
    assert "너무 매웠어요" in call["messages"][0]["content"]


def test_no_comment_means_no_llm_call():
    client = FakeClient({"changes": []})
    assert fb.learn_from_comment(client, "u1", "떡볶이", 1, "  ") == []
    assert client.calls == []


def test_llm_error_is_swallowed(monkeypatch):
    import anthropic, httpx
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.invalid"))
    assert fb.learn_from_comment(FakeClient(error=err), "u1", "x", 1, "맛있다") == []


def test_record_feedback_rejects_bad_rating():
    with pytest.raises(ValueError):
        fb.record_feedback("u1", "m1", 3, None)


def test_agent_record_feedback_tool(monkeypatch):
    recorded = []
    monkeypatch.setattr(agent, "latest_meal_id", lambda uid, title: "meal-9" if title == "된장국" else None)
    monkeypatch.setattr(agent, "record_feedback", lambda uid, mid, r, c: recorded.append((uid, mid, r, c)))
    monkeypatch.setattr(agent, "learn_from_comment", lambda client, uid, title, r, c: ["싫어함: 짠맛"] if c else [])
    handlers = agent.make_tool_handlers("u1", AgentState(), client=object())
    tool = lambda inp: NS(type="tool_use", id="x", name="record_feedback", input=inp)
    res = run_tool(handlers, tool({"recipe_title": "된장국", "rating": -1, "comment": "짰어"}))
    assert not res.get("is_error") and "짠맛" in res["content"]
    assert recorded == [("u1", "meal-9", -1, "짰어")]
    assert run_tool(handlers, tool({"recipe_title": "피자", "rating": 1}))["is_error"]
    assert run_tool(handlers, tool({"recipe_title": "된장국", "rating": 5}))["is_error"]
