"""재고 화면을 DB 없이 가짜 데이터로 돌려 보는 테스트 (Streamlit AppTest)."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import lib.inventory as inv
from lib.inventory_rules import ItemInput, expiry_for_new, validate
from lib.models import AppUser, CatalogItem, InventoryItem

TODAY = date(2026, 11, 26)
USER = AppUser("user-1", "a@example.com")
CATALOG = [
    CatalogItem(1, "두부", [], "달걀·두부", 5, "fridge"),
    CatalogItem(2, "대파", ["파"], "채소", 10, "fridge"),
]


@pytest.fixture
def store(monkeypatch):
    """DB 대신 쓰는 메모리 저장소."""
    items: list[InventoryItem] = [
        InventoryItem("a", "두부", 1, 1, "모", TODAY, date(2026, 11, 27), "estimated", "active"),
        InventoryItem("b", "대파", 2, 1, "단", TODAY, date(2026, 12, 6), "estimated", "active"),
    ]
    calls: list[tuple] = []

    def fake_add(user_id: str, item: ItemInput):
        assert user_id == USER.id
        item = validate(item)
        expires, source, match = expiry_for_new(item, CATALOG)
        items.append(
            InventoryItem("new", item.name, match.id if match else None, item.quantity,
                          item.unit, item.purchased_at, expires, source, "active")
        )
        calls.append(("add", item.name, expires))

    monkeypatch.setattr(inv, "get_catalog", lambda: CATALOG)
    monkeypatch.setattr(inv, "get_inventory", lambda user_id: [i for i in items if user_id == USER.id])
    monkeypatch.setattr(inv, "add_item", fake_add)
    monkeypatch.setattr(inv, "set_status", lambda u, i, s: calls.append(("status", i, s)))
    monkeypatch.setattr(inv, "delete_item", lambda u, i: calls.append(("delete", i)))
    monkeypatch.setattr(inv, "update_item", lambda u, o, c: calls.append(("update", o.id)))
    monkeypatch.setattr("lib.dates.today_kst", lambda now=None: TODAY)
    return items, calls


def run_page():
    at = AppTest.from_file("views/inventory.py", default_timeout=60)
    at.session_state["user"] = USER
    at.run()
    assert not at.exception, at.exception
    return at


def test_page_lists_items_with_dday(store):
    at = run_page()
    df = at.dataframe[0].value if at.dataframe else None  # data_editor 는 arrow 로 렌더됨
    assert "재료 2개 · 3일 안에 써야 할 재료 1개" in at.caption[0].value
    assert at.title[0].value == "재고"
    assert df is None or len(df) == 2


def test_add_item_estimates_expiry_and_clears_form(store):
    items, calls = store
    at = run_page()
    at.selectbox(key="add_name").select("대파")
    at.run()
    assert any("12-06" in c.value or "2026-12-06" in c.value for c in at.caption)

    at.button[0].click()  # 추가
    at.run()
    assert not at.exception
    assert calls[-1] == ("add", "대파", date(2026, 12, 6))
    assert at.session_state["add_name"] is None  # 입력칸 비워짐


def test_add_without_name_shows_error(store):
    # (목록에 없는 새 이름은 AppTest가 아직 못 다뤄서, 그 규칙은 test_inventory_rules.py 에서 검사)
    items, calls = store
    at = run_page()
    at.button[0].click()
    at.run()
    assert not calls
    assert "재료 이름을 입력" in at.error[0].value


def test_page_requires_login(store):
    at = AppTest.from_file("views/inventory.py", default_timeout=60)
    at.run()
    assert "로그인이 필요" in at.warning[0].value
    assert not at.title  # 재고 내용은 안 보임
