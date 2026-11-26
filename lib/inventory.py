"""재고 DB 읽기·쓰기. RLS 덕분에 로그인한 사용자의 재고만 다룹니다."""
from __future__ import annotations

from datetime import date
from typing import Literal

import streamlit as st

from lib.dates import add_days, parse_date, today_kst
from lib.db import get_client
from lib.inventory_rules import ItemInput, expiry_for_new, expiry_for_update, validate
from lib.models import CatalogItem, InventoryItem


def _to_item(row: dict) -> InventoryItem:
    return InventoryItem(
        id=row["id"],
        name=row["name"],
        catalog_id=row.get("catalog_id"),
        quantity=float(row["quantity"]),
        unit=row.get("unit"),
        purchased_at=parse_date(row["purchased_at"]),
        expires_at=parse_date(row["expires_at"]),
        expiry_source=row["expiry_source"],
        status=row["status"],
    )


# ── 읽기 ─────────────────────────────────────
def get_inventory() -> list[InventoryItem]:
    """사용 중인 재고 전체, 유통기한 빠른 순."""
    res = (
        get_client()
        .table("inventory")
        .select("*")
        .eq("status", "active")
        .order("expires_at")
        .order("created_at")
        .execute()
    )
    return [_to_item(r) for r in res.data]


def get_expiring(days: int, include_expired: bool = False) -> list[InventoryItem]:
    """팀 공용 함수 (PLAN.md 11-2) — 오늘부터 D-days 이내에 유통기한이 끝나는 재료.

    이미 지난 재료는 구출 대상이 아니라서 기본으로 빼고, include_expired=True 면 포함해요.
    유통기한 빠른 순으로 정렬됩니다.
    """
    today = today_kst()
    query = (
        get_client()
        .table("inventory")
        .select("*")
        .eq("status", "active")
        .lte("expires_at", add_days(today, days).isoformat())
    )
    if not include_expired:
        query = query.gte("expires_at", today.isoformat())
    res = query.order("expires_at").execute()
    return [_to_item(r) for r in res.data]


@st.cache_data(ttl=600, show_spinner=False)
def _load_catalog_rows() -> list[dict]:
    res = (
        get_client()
        .table("ingredient_catalog")
        .select("id, name, aliases, category, default_shelf_days, storage")
        .order("name")
        .execute()
    )
    return res.data


def get_catalog() -> list[CatalogItem]:
    """재료 카탈로그 전체 (모든 사용자 공용이라 10분간 캐시)."""
    return [CatalogItem(**r) for r in _load_catalog_rows()]


# ── 쓰기 ─────────────────────────────────────
def add_item(item: ItemInput) -> None:
    """재료 추가. 입력이 잘못되면 ValueError."""
    item = validate(item)
    expires, source, match = expiry_for_new(item, get_catalog())
    get_client().table("inventory").insert(
        {
            "name": item.name,
            "catalog_id": match.id if match else None,
            "quantity": item.quantity,
            "unit": item.unit,
            "purchased_at": item.purchased_at.isoformat(),
            "expires_at": expires.isoformat(),
            "expiry_source": source,
        }
    ).execute()


def update_item(original: InventoryItem, changed: ItemInput) -> None:
    """재료 수정. 입력이 잘못되면 ValueError."""
    changed = validate(changed)
    expires, source, match = expiry_for_update(
        changed, original.purchased_at, original.expires_at, original.expiry_source, get_catalog()
    )
    get_client().table("inventory").update(
        {
            "name": changed.name,
            "catalog_id": match.id if match else None,
            "quantity": changed.quantity,
            "unit": changed.unit,
            "purchased_at": changed.purchased_at.isoformat(),
            "expires_at": expires.isoformat(),
            "expiry_source": source,
        }
    ).eq("id", original.id).execute()


def set_status(item_id: str, status: Literal["used", "discarded"]) -> None:
    """다 먹음(used) / 버림(discarded) — 기록은 남겨 대시보드 통계에 씀."""
    get_client().table("inventory").update({"status": status}).eq("id", item_id).execute()


def delete_item(item_id: str) -> None:
    """잘못 등록한 재료 완전 삭제 (통계에 남지 않음)."""
    get_client().table("inventory").delete().eq("id", item_id).execute()


def days_left(item: InventoryItem, today: date) -> int:
    return (item.expires_at - today).days
