"""재료 등록(영수증·냉장고 사진) — 순수 함수. Claude 응답 검사와 사진 줄이기.

Claude 가 돌려준 값은 믿지 않고 여기서 한 번 더 검사해요 (이름 길이, 수량, 날짜 형식, 미래 날짜 등).
"""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from PIL import Image, ImageOps

MAX_IMAGE_SIDE = 1568  # Claude 비전 권장 최대 (넘으면 서버가 줄이니 미리 줄여 비용·시간 절약)
MAX_ITEMS = 40
LOW_CONFIDENCE = 0.6
STORAGES = ("fridge", "freezer", "room")
# Claude 가 식재료라고 해도 이 단어가 있으면 빼요 (영수증의 생활용품·할인 줄)
NON_FOOD_WORDS = ("봉투", "할인", "포인트", "쿠폰", "적립", "키친타올", "타올", "휴지", "티슈", "세제", "랩", "호일", "지퍼백", "건전지", "합계", "부가세")


@dataclass
class DraftItem:
    """인식 결과 한 줄 (확인 표에 보여 주고 사용자가 고친 뒤 저장)."""

    name: str
    quantity: float
    unit: Optional[str]
    purchased_at: date
    expires_at: Optional[date]  # 라벨에 유통기한이 보일 때만
    confidence: float

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE


@dataclass
class ShelfEstimate:
    """카탈로그에 없는 재료의 보통 보관 일수 추정."""

    name: str
    category: Optional[str]
    shelf_days: int
    storage: str


def prepare_image(data: bytes) -> tuple[str, str]:
    """사진 → (media_type, base64). 휴대폰 사진 회전 바로잡고, 긴 변 1568px 이하 JPEG 로."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    return "image/jpeg", base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str):
        return None
    m = re.match(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})", value.strip())
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _core_name(line_text: str) -> str:
    """영수증 줄에서 괄호·숫자·단위를 뺀 알맹이. 예: '대파(1단)' → '대파', '서울우유 1L' → '서울우유'"""
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", line_text)
    text = re.sub(r"\d+(\.\d+)?\s*(kg|g|ml|l|L|개|구|입|팩|봉|매|병|단)?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_non_food(*texts: str) -> bool:
    return any(w in (t or "") for t in texts for w in NON_FOOD_WORDS)


def parse_extraction(tool_input: Any, today: date) -> list[DraftItem]:
    """Claude 도구 입력 → 검사한 DraftItem 목록. 이상한 줄은 버리고, 빈 값은 기본값으로.

    안전장치
    - is_food 가 false 이거나 생활용품 단어가 있으면 빼요.
    - 원문(line_text)이 짧은 재료 이름(3자 이하)인데 Claude 가 다른 이름을 냈으면 원문을 써요
      (예: 영수증 '고수' → Claude '고추' 로 바꿔치기 방지).
    """
    if not isinstance(tool_input, dict):
        return []
    receipt_day = _parse_date(tool_input.get("purchase_date"))
    if receipt_day is None or receipt_day > today:
        receipt_day = today  # 영수증 날짜가 없거나 미래면 오늘
    items = tool_input.get("items")
    if not isinstance(items, list):
        return []

    out: list[DraftItem] = []
    for raw in items[:MAX_ITEMS]:
        if not isinstance(raw, dict) or raw.get("is_food") is False:
            continue
        line_text = re.sub(r"\s+", " ", str(raw.get("line_text") or "")).strip()
        name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()
        core = _core_name(line_text)
        if core and len(core) <= 3 and name != core and not core.isascii():
            name = core
        if not name or len(name) > 50 or _is_non_food(line_text, name):
            continue
        qty = raw.get("quantity")
        quantity = float(qty) if isinstance(qty, (int, float)) and not isinstance(qty, bool) and 0 < qty <= 10000 else 1.0
        unit = str(raw.get("unit") or "").strip() or None
        if unit and len(unit) > 10:
            unit = None
        expires = _parse_date(raw.get("expires_at"))
        conf = raw.get("confidence")
        confidence = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.5
        out.append(DraftItem(name, quantity, unit, receipt_day, expires, max(0.0, min(1.0, confidence))))
    return out


def parse_shelf_estimates(tool_input: Any, asked: list[str]) -> list[ShelfEstimate]:
    """보관 일수 추정 결과 검사. 물어본 이름에 대한 답만, 일수 1~730 범위만 받아요."""
    asked_set = set(asked)
    rows = tool_input.get("items") if isinstance(tool_input, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[ShelfEstimate] = []
    for r in rows:
        if not isinstance(r, dict) or r.get("name") not in asked_set:
            continue
        if r.get("is_food") is False or _is_non_food(r["name"]):
            continue  # 먹는 게 아니면 공용 카탈로그에 넣지 않아요
        days = r.get("shelf_days")
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 730:
            continue
        storage = r.get("storage") if r.get("storage") in STORAGES else "fridge"
        category = str(r.get("category") or "").strip()[:20] or None
        out.append(ShelfEstimate(r["name"], category, days, storage))
    return out
