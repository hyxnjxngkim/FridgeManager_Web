"""에이전트 반복 처리를 가짜 Claude 로 검사 (네트워크·DB 없음)."""
from datetime import date
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest

import lib.agent as agent
from lib.agent import AgentState, run_tool, run_turn
from lib.fake_recipes import SAMPLE_RECIPES
from lib.models import InventoryItem, Preference, RecipeMatch

TODAY = date(2026, 11, 26)


class FakeStream:
    def __init__(self, text, final):
        self._text, self._final = text, final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        yield from self._text

    def get_final_message(self):
        return self._final


class FakeClient:
    """미리 정한 응답을 차례로 돌려주는 가짜 Claude."""

    def __init__(self, turns):
        self.turns, self.calls = list(turns), []
        self.messages = NS(stream=self._stream)

    def _stream(self, **kw):
        self.calls.append(kw)
        text, blocks, stop = self.turns.pop(0)
        return FakeStream(text, NS(stop_reason=stop, content=blocks))


def text_block(t):
    return NS(type="text", text=t)


def tool_block(id, name, inp):
    return NS(type="tool_use", id=id, name=name, input=inp)


@pytest.fixture(autouse=True)
def fake_data(monkeypatch):
    saved = []
    tofu = InventoryItem("t1", "두부", 1, 1, "모", TODAY, date(2026, 11, 27), "estimated", "active")
    monkeypatch.setattr(agent, "today_kst", lambda: TODAY)
    monkeypatch.setattr(agent, "get_expiring", lambda uid, days: [tofu])
    monkeypatch.setattr(agent, "get_inventory", lambda uid: [tofu])
    monkeypatch.setattr(agent, "get_catalog", lambda: [])
    monkeypatch.setattr(agent, "search_recipes", lambda uid, ing, **kw: [RecipeMatch(SAMPLE_RECIPES[0], 3.0, ["두부"], [])])
    monkeypatch.setattr(agent, "get_preferences", lambda uid: [Preference("p1", "allergy", "땅콩")])
    monkeypatch.setattr(agent, "save_preference", lambda uid, k, v: saved.append((uid, k, v)) or Preference("p2", k, v))
    return saved


def test_plain_answer_streams_text_and_records_history():
    client = FakeClient([(["안녕", "하세요"], [text_block("안녕하세요")], "end_turn")])
    state = AgentState()
    out = "".join(run_turn(client, state, "u1", "안녕?"))
    assert out == "안녕하세요"
    assert [m["role"] for m in state.messages] == ["user", "assistant"]
    assert "2026-11-26" in state.messages[0]["content"][0]["text"]  # 오늘 날짜 전달


def test_tool_loop_search_then_prepare_cooking_sets_pending():
    client = FakeClient([
        ([], [tool_block("a", "get_expiring", {"days": 3})], "tool_use"),
        ([], [tool_block("b", "search_recipes", {"ingredients": ["두부"]})], "tool_use"),
        ([], [tool_block("c", "prepare_cooking", {"recipe_id": SAMPLE_RECIPES[0].id})], "tool_use"),
        (["확인해 주세요"], [text_block("확인해 주세요")], "end_turn"),
    ])
    state = AgentState()
    out = "".join(run_turn(client, state, "u1", "두부조림 만들게"))
    assert "확인해 주세요" in out
    assert state.tools_used == ["get_expiring", "search_recipes", "prepare_cooking"]
    assert [m.recipe.title for m in state.shown_matches] == ["두부조림"]
    assert state.pending_cook and state.pending_cook.lines[0].item_id == "t1"
    # 도구 결과는 tool_use 바로 다음 user 메시지로
    results = state.messages[2]["content"]
    assert results[0]["tool_use_id"] == "a" and not results[0].get("is_error")


def test_save_preference_tool_uses_current_user(fake_data):
    client = FakeClient([
        ([], [tool_block("a", "save_preference", {"kind": "allergy", "value": "땅콩"})], "tool_use"),
        (["기억했어요"], [text_block("기억했어요")], "end_turn"),
    ])
    "".join(run_turn(client, AgentState(), "u42", "나 땅콩 알레르기"))
    assert fake_data == [("u42", "allergy", "땅콩")]


def test_prepare_cooking_rejects_unknown_recipe():
    handlers = agent.make_tool_handlers("u1", AgentState())
    res = run_tool(handlers, tool_block("x", "prepare_cooking", {"recipe_id": "made-up"}))
    assert res["is_error"] and "search_recipes" in res["content"]


def test_bad_tool_input_is_error_not_crash():
    handlers = agent.make_tool_handlers("u1", AgentState())
    assert run_tool(handlers, tool_block("x", "search_recipes", {"ingredients": "두부"}))["is_error"]
    assert run_tool(handlers, tool_block("y", "nope", {}))["is_error"]


def test_api_error_rolls_back_history():
    req = httpx.Request("POST", "https://example.invalid")

    class Boom(FakeClient):
        def _stream(self, **kw):
            raise anthropic.APIConnectionError(request=req)

    state = AgentState()
    state.messages = [{"role": "user", "content": "이전"}, {"role": "assistant", "content": "답"}]
    out = "".join(run_turn(Boom([]), state, "u1", "또"))
    assert "연결하지 못했어요" in out
    assert len(state.messages) == 2  # 이번 턴 기록은 지워짐


def test_notes_are_passed_once():
    client = FakeClient([(["ok"], [text_block("ok")], "end_turn")] * 2)
    state = AgentState(notes=["두부조림을 만들어 재고를 뺐어요"])
    "".join(run_turn(client, state, "u1", "다음은?"))
    assert "두부조림" in state.messages[0]["content"][0]["text"] and state.notes == []
