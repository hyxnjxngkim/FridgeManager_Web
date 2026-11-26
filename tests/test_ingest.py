"""사진 인식·저장을 가짜 Claude 로 검사 (네트워크·DB 없음)."""
import io
from datetime import date
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest
from PIL import Image

import lib.ingest as ingest
from lib.config import CLAUDE_MODEL, CLAUDE_MODEL_SMART
from lib.ingest import IngestError, estimate_shelf_days, extract_items, save_drafts
from lib.ingest_rules import DraftItem, ShelfEstimate
from lib.models import CatalogItem

TODAY = date(2026, 11, 26)


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


class FakeClient:
    def __init__(self, tool_input=None, stop="tool_use", error=None, name="save_ingredients"):
        self.calls = []
        self.messages = NS(create=self._create)
        self._input, self._stop, self._error, self._name = tool_input, stop, error, name

    def _create(self, **kw):
        self.calls.append(kw)
        if self._error:
            raise self._error
        blocks = [] if self._stop == "refusal" else [NS(type="tool_use", id="t", name=self._name, input=self._input)]
        return NS(stop_reason=self._stop, content=blocks)


def test_receipt_uses_haiku_fridge_uses_sonnet_with_forced_tool_and_image():
    for kind, model in (("receipt", CLAUDE_MODEL), ("fridge", CLAUDE_MODEL_SMART)):
        c = FakeClient({"items": [{"name": "두부", "quantity": 1, "confidence": 0.9}]})
        out = extract_items(c, png(), kind, ["두부", "대파"], TODAY)
        call = c.calls[0]
        assert call["model"] == model
        assert call["tool_choice"] == {"type": "tool", "name": "save_ingredients"}
        content = call["messages"][0]["content"]
        assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
        assert "두부, 대파" in content[1]["text"]
        assert out[0].name == "두부"


def test_bad_image_refusal_and_api_errors_become_ingest_error():
    with pytest.raises(IngestError, match="사진 파일"):
        extract_items(FakeClient({}), b"not an image", "receipt", [], TODAY)
    with pytest.raises(IngestError, match="처리할 수 없어요"):
        extract_items(FakeClient(stop="refusal"), png(), "receipt", [], TODAY)
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.invalid"))
    with pytest.raises(IngestError, match="연결하지 못했어요"):
        extract_items(FakeClient(error=err), png(), "fridge", [], TODAY)


def test_estimate_shelf_days_one_call_and_errors_are_empty():
    c = FakeClient({"items": [{"name": "고수", "shelf_days": 5, "storage": "fridge"}]}, name="save_shelf_days")
    assert [e.name for e in estimate_shelf_days(c, ["고수", "라임"])] == ["고수"]
    assert len(c.calls) == 1 and c.calls[0]["model"] == CLAUDE_MODEL
    assert estimate_shelf_days(c, []) == [] and len(c.calls) == 1
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.invalid"))
    assert estimate_shelf_days(FakeClient(error=err), ["고수"]) == []


def test_save_drafts_estimates_only_unknown_without_label(monkeypatch):
    asked, added, saved_items = [], [], []
    monkeypatch.setattr(ingest, "get_catalog", lambda: [CatalogItem(1, "두부", [], None, 5, "fridge")])
    monkeypatch.setattr(ingest, "estimate_shelf_days", lambda client, names: asked.append(names) or [ShelfEstimate("고수", "채소", 5, "fridge")])
    monkeypatch.setattr(ingest, "add_to_catalog", lambda est: added.extend(est))

    def fake_add(uid, item):
        if item.name == "라임":
            raise ValueError("'라임'은(는) 보관 기간을 몰라요.")
        saved_items.append((uid, item.name))

    monkeypatch.setattr(ingest, "add_item", fake_add)
    drafts = [
        DraftItem("두부", 1, "모", TODAY, None, 1),
        DraftItem("고수", 1, "단", TODAY, None, 1),
        DraftItem("라임", 2, "개", TODAY, None, 1),
        DraftItem("치즈", 1, "팩", TODAY, date(2026, 12, 20), 1),  # 라벨 유통기한 있으면 추정 안 함
    ]
    saved, failed = save_drafts("u1", drafts, client=object())
    assert asked == [["고수", "라임"]]  # 한 번에, 정렬해서
    assert [e.name for e in added] == ["고수"]
    assert saved == ["두부", "고수", "치즈"] and failed[0][0] == "라임"
    assert all(uid == "u1" for uid, _ in saved_items)
