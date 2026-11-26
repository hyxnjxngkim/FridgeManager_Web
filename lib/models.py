"""팀 공용 데이터 모양 — 고칠 때는 상대에게 먼저 알리고 바로 PR로 올리세요 (PLAN.md 11-4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

StorageType = Literal["fridge", "freezer", "room"]
InventoryStatus = Literal["active", "used", "discarded"]
# estimated: 카탈로그로 추정 / label: 사진·영수증에서 읽음 / manual: 사용자가 직접 입력
ExpirySource = Literal["estimated", "label", "manual"]


# ── 재료 카탈로그 ─────────────────────────────
@dataclass
class CatalogItem:
    id: int
    name: str
    aliases: list[str]
    category: Optional[str]
    default_shelf_days: int
    storage: StorageType


# ── 재고 ─────────────────────────────────────
@dataclass
class InventoryItem:
    id: str
    name: str
    catalog_id: Optional[int]
    quantity: float
    unit: Optional[str]
    purchased_at: date
    expires_at: date
    expiry_source: ExpirySource
    status: InventoryStatus


# ── 레시피 (Phase 3, 팀원 B) ──────────────────
@dataclass
class RecipeIngredient:
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    optional: bool = False


@dataclass
class Recipe:
    id: str
    title: str
    ingredients: list[RecipeIngredient]
    steps: str
    cook_minutes: Optional[int] = None
    servings: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)
    source_name: Optional[str] = None
    source_url: Optional[str] = None


@dataclass
class RecipeMatch:
    """search_recipes() 결과 한 개."""

    recipe: Recipe
    score: float
    uses_expiring: list[str] = field(default_factory=list)  # 이 레시피가 쓰는 임박 재료
    missing: list[str] = field(default_factory=list)  # 재고에 없는 재료
