"""재료 카탈로그 매칭 — 순수 함수."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lib.dates import add_days
from lib.models import CatalogItem


def _normalize(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def match_catalog(name: str, catalog: list[CatalogItem]) -> Optional[CatalogItem]:
    """이름이나 별칭이 정확히 같은 카탈로그 항목 ('파' → '대파', '계란' → '달걀')."""
    key = _normalize(name)
    if not key:
        return None
    for item in catalog:
        if _normalize(item.name) == key or any(_normalize(a) == key for a in item.aliases):
            return item
    return None


def estimate_expiry(purchased_at: date, item: CatalogItem) -> date:
    """구입일 + 보통 보관 일수 = 추정 유통기한."""
    return add_days(purchased_at, item.default_shelf_days)
