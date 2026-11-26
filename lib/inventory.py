"""재고 DB 읽기·쓰기.

모든 함수는 user_id 를 받아서 그 사용자의 재고만 다뤄요 (DB에 RLS가 없으므로 코드에서 걸러요).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

import streamlit as st

from lib.dates import add_days, today_kst
from lib.db import execute, fetch_all
from lib.inventory_rules import ItemInput, expiry_for_new, expiry_for_update, validate
from lib.models import CatalogItem, InventoryItem

_COLUMNS = "id, name, catalog_id, quantity, unit, purchased_at, expires_at, expiry_source, status"


def _to_item(row: dict) -> InventoryItem:
    return InventoryItem(
        id=str(row["id"]),
        name=row["name"],
        catalog_id=row["catalog_id"],
        quantity=float(row["quantity"]),
        unit=row["unit"],
        purchased_at=row["purchased_at"],
        expires_at=row["expires_at"],
        expiry_source=row["expiry_source"],
        status=row["status"],
    )


# ── 읽기 ─────────────────────────────────────
def get_inventory(user_id: str) -> list[InventoryItem]:
    """사용 중인 재고 전체, 유통기한 빠른 순."""
    rows = fetch_all(
        f"select {_COLUMNS} from inventory"
        " where user_id = %s and status = 'active'"
        " order by expires_at, created_at",
        (user_id,),
    )
    return [_to_item(r) for r in rows]


def get_expiring(user_id: str, days: int, include_expired: bool = False) -> list[InventoryItem]:
    """팀 공용 함수 (PLAN.md 11-2) — 오늘부터 D-days 이내에 유통기한이 끝나는 재료.

    이미 지난 재료는 구출 대상이 아니라서 기본으로 빼고, include_expired=True 면 포함해요.
    유통기한 빠른 순으로 정렬됩니다.
    """
    today = today_kst()
    sql = (
        f"select {_COLUMNS} from inventory"
        " where user_id = %s and status = 'active' and expires_at <= %s"
    )
    params: list = [user_id, add_days(today, days)]
    if not include_expired:
        sql += " and expires_at >= %s"
        params.append(today)
    rows = fetch_all(sql + " order by expires_at", params)
    return [_to_item(r) for r in rows]


@st.cache_data(ttl=600, show_spinner=False)
def _load_catalog_rows() -> list[dict]:
    return fetch_all(
        "select id, name, aliases, category, default_shelf_days, storage"
        " from ingredient_catalog order by name"
    )


def get_catalog() -> list[CatalogItem]:
    """재료 카탈로그 전체 (모든 사용자 공용이라 10분간 캐시)."""
    return [CatalogItem(**r) for r in _load_catalog_rows()]


# ── 쓰기 ─────────────────────────────────────
def add_item(user_id: str, item: ItemInput) -> None:
    """재료 추가. 입력이 잘못되면 ValueError."""
    item = validate(item)
    expires, source, match = expiry_for_new(item, get_catalog())
    execute(
        "insert into inventory"
        " (user_id, name, catalog_id, quantity, unit, purchased_at, expires_at, expiry_source)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            user_id,
            item.name,
            match.id if match else None,
            item.quantity,
            item.unit,
            item.purchased_at,
            expires,
            source,
        ),
    )


def update_item(user_id: str, original: InventoryItem, changed: ItemInput) -> None:
    """재료 수정. 입력이 잘못되면 ValueError."""
    changed = validate(changed)
    expires, source, match = expiry_for_update(
        changed, original.purchased_at, original.expires_at, original.expiry_source, get_catalog()
    )
    execute(
        "update inventory set name = %s, catalog_id = %s, quantity = %s, unit = %s,"
        " purchased_at = %s, expires_at = %s, expiry_source = %s"
        " where id = %s and user_id = %s",
        (
            changed.name,
            match.id if match else None,
            changed.quantity,
            changed.unit,
            changed.purchased_at,
            expires,
            source,
            original.id,
            user_id,
        ),
    )


def set_status(user_id: str, item_id: str, status: Literal["used", "discarded"]) -> None:
    """다 먹음(used) / 버림(discarded) — 기록은 남겨 대시보드 통계에 씀."""
    execute(
        "update inventory set status = %s where id = %s and user_id = %s",
        (status, item_id, user_id),
    )


def delete_item(user_id: str, item_id: str) -> None:
    """잘못 등록한 재료 완전 삭제 (통계에 남지 않음)."""
    execute("delete from inventory where id = %s and user_id = %s", (item_id, user_id))


def days_left(item: InventoryItem, today: date) -> int:
    return (item.expires_at - today).days
