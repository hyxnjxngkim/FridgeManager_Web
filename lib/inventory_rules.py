"""재고 입력 검사와 유통기한 결정 규칙 — 순수 함수 (DB 없이 테스트 가능)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from lib.catalog import estimate_expiry, match_catalog
from lib.models import CatalogItem, ExpirySource


@dataclass
class ItemInput:
    name: str
    quantity: float
    unit: Optional[str]
    purchased_at: date
    expires_at: Optional[date] = None


def validate(item: ItemInput) -> ItemInput:
    """입력을 다듬고 검사. 문제가 있으면 ValueError(사용자에게 보여줄 메시지)."""
    name = (item.name or "").strip()
    unit = (item.unit or "").strip() or None
    if not name:
        raise ValueError("재료 이름을 입력해 주세요.")
    if len(name) > 50:
        raise ValueError("재료 이름이 너무 길어요 (50자 이하).")
    if item.quantity is None or item.quantity <= 0:
        raise ValueError("수량은 0보다 커야 해요.")
    if unit and len(unit) > 10:
        raise ValueError("단위가 너무 길어요 (10자 이하).")
    if item.purchased_at is None:
        raise ValueError("구입일을 입력해 주세요.")
    return ItemInput(name, float(item.quantity), unit, item.purchased_at, item.expires_at)


def expiry_for_new(
    item: ItemInput, catalog: list[CatalogItem]
) -> tuple[date, ExpirySource, Optional[CatalogItem]]:
    """새 재료의 유통기한: 직접 입력 > 카탈로그 추정 > (모르면) 오류."""
    match = match_catalog(item.name, catalog)
    if item.expires_at:
        return item.expires_at, "manual", match
    if match:
        return estimate_expiry(item.purchased_at, match), "estimated", match
    raise ValueError(f"'{item.name}'은(는) 보관 기간을 몰라요. 유통기한을 직접 입력해 주세요.")


def expiry_for_update(
    item: ItemInput,
    original_purchased: date,
    original_expires: date,
    original_source: ExpirySource,
    catalog: list[CatalogItem],
) -> tuple[date, ExpirySource, Optional[CatalogItem]]:
    """수정할 때: 유통기한을 직접 바꾸면 manual, 추정값인데 구입일만 바뀌면 다시 추정."""
    match = match_catalog(item.name, catalog)
    expires = item.expires_at or original_expires
    if expires != original_expires:
        return expires, "manual", match
    if original_source == "estimated" and match and item.purchased_at != original_purchased:
        return estimate_expiry(item.purchased_at, match), "estimated", match
    return expires, original_source, match
