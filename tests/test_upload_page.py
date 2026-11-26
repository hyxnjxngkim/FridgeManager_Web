from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import lib.ingest as ingest
import lib.inventory as inv
from lib.ingest_rules import DraftItem
from lib.models import AppUser

ROOT = Path(__file__).resolve().parent.parent
USER = AppUser("user-1", "a@example.com")
TODAY = date(2026, 11, 26)


def app():
    at = AppTest.from_file(str(ROOT / "views" / "upload.py"), default_timeout=60)
    at.session_state["user"] = USER
    return at


def test_without_aws_shows_warning(monkeypatch):
    monkeypatch.setattr("lib.llm.llm_unavailable_reason", lambda: "AWS 자격증명이 없어요.")
    at = app()
    at.run()
    assert not at.exception and "사진 인식을 쓸 수 없어요" in at.warning[0].value


def test_review_table_and_save(monkeypatch):
    saved = []
    monkeypatch.setattr("lib.llm.llm_unavailable_reason", lambda: None)
    monkeypatch.setattr("lib.llm.get_client", lambda: object())
    monkeypatch.setattr(inv, "get_catalog", lambda: [])
    monkeypatch.setattr("lib.dates.today_kst", lambda now=None: TODAY)
    fake = lambda uid, items, client=None: saved.append([(i.name, i.quantity, i.expires_at) for i in items]) or ([i.name for i in items], [])
    monkeypatch.setattr(ingest, "save_drafts", fake)
    at = app()
    at.session_state["ingest_drafts"] = [
        DraftItem("두부", 2, "모", TODAY, None, 0.95),
        DraftItem("고수", 1, "단", TODAY, None, 0.4),
    ]
    at.run()
    assert not at.exception, at.exception
    assert "찾은 재료 2개" in at.subheader[0].value
    next(b for b in at.button if b.label == "재고에 저장").click().run()
    assert not at.exception, at.exception
    assert saved == [[("두부", 2.0, None), ("고수", 1.0, None)]]
    assert "ingest_drafts" not in at.session_state  # 저장 뒤 비워짐
