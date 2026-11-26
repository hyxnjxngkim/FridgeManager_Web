"""재료 등록 (Phase 2) — 영수증·냉장고 사진에서 재료 뽑기, 처음 보는 재료의 보관 일수 추정, 저장.

- 영수증: Haiku 4.5 (CLAUDE_MODEL) — 글자 위주라 싼 모델로 충분
- 냉장고 사진: Sonnet 4.6 (CLAUDE_MODEL_SMART) — 여러 재료를 알아봐야 해서. Sonnet 은 여기서만 써요.
- 결과는 정해진 도구 형식으로만 받고(tool_choice 고정), lib/ingest_rules.py 에서 다시 검사해요.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

import anthropic

from lib.catalog import match_catalog
from lib.config import CLAUDE_MODEL, CLAUDE_MODEL_SMART
from lib.db import transaction
from lib.ingest_rules import DraftItem, ShelfEstimate, parse_extraction, parse_shelf_estimates, prepare_image
from lib.inventory import _load_catalog_rows, add_item, get_catalog
from lib.inventory_rules import ItemInput

Kind = Literal["receipt", "fridge"]


class IngestError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 오류."""


EXTRACT_TOOL = {
    "name": "save_ingredients",
    "description": "사진에서 찾은 식재료 목록을 저장",
    "input_schema": {
        "type": "object",
        "properties": {
            "purchase_date": {"type": "string", "description": "영수증의 구매 날짜 YYYY-MM-DD (없으면 생략)"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line_text": {"type": "string", "description": "영수증 줄(또는 사진의 이름표) 글자를 그대로 옮겨 적기"},
                        "is_food": {"type": "boolean", "description": "먹는 것이면 true, 봉투·할인·생활용품이면 false"},
                        "name": {"type": "string", "description": "line_text 에서 브랜드·용량을 뺀 일반 재료 이름"},
                        "quantity": {"type": "number", "description": "개수 또는 양"},
                        "unit": {"type": "string", "description": "개, 팩, 봉, 모, 병, 단, g, ml 등"},
                        "expires_at": {"type": "string", "description": "포장에 적힌 유통기한 YYYY-MM-DD (보일 때만)"},
                        "confidence": {"type": "number", "description": "0~1, 확실하면 1"},
                    },
                    "required": ["line_text", "is_food", "name", "quantity", "confidence"],
                },
            },
        },
        "required": ["items"],
    },
}

PROMPTS = {
    "receipt": (
        "장보기 영수증 사진이에요. 상품 줄마다 하나씩, 한 줄도 빠짐없이 적어 주세요.\n"
        "- line_text 에는 영수증 줄 글자를 그대로 옮겨 적고, 먹는 것인지 is_food 로 표시해요.\n"
        "- 냉동식품(만두 등)·가공식품·음료·양념도 먹는 것이면 넣어요.\n"
        "- 봉투, 할인, 포인트, 세제·휴지·키친타올 같은 생활용품 줄은 빼요.\n"
        "- 이름은 브랜드·용량을 뺀 일반 재료 이름으로 (예: '풀무원 국산콩두부 300g' → '두부', 'CJ 비비고 왕교자' → '냉동만두').\n"
        "- 아래 목록은 참고용이에요. 정확히 같은 재료일 때만 목록의 이름을 쓰고, 목록에 없는 재료는 "
        "영수증에 적힌 재료 이름을 그대로 써요. 비슷한 다른 재료로 절대 바꾸지 마요 (예: '고수'는 '고수').\n"
        "- 수량은 산 개수, 단위는 포장 단위(개·팩·봉·모·병·단). 영수증에 단위가 안 보이면 '개'.\n"
        "- 영수증의 구매 날짜가 보이면 purchase_date 에 넣어요. 유통기한은 영수증에 없으면 비워요.\n"
        "- confidence 는 글자를 정확히 읽었을 때만 0.9 이상, 흐리거나 짐작했으면 0.6 미만."
    ),
    "fridge": (
        "냉장고 안을 찍은 사진이에요. 보이는 식재료를 뽑아 주세요. line_text 에는 이름표·포장 글자를 그대로(안 보이면 생김새를 짧게), is_food 는 true.\n"
        "- 확실히 알아볼 수 있는 것만. 양념통·음료도 식재료면 넣어요.\n"
        "- 이름은 일반 재료 이름으로. 아래 목록은 참고용이에요: 정확히 같은 재료일 때만 목록의 이름을 쓰고, "
        "아니면 보이는 재료 이름을 그대로 써요. 비슷한 다른 재료로 바꾸지 마요.\n"
        "- 수량은 보이는 대로 대략, 단위는 개·팩·봉·모·병·단 등.\n"
        "- 포장의 유통기한 글자가 읽히면 expires_at 에 넣어요.\n"
        "- 알아보기 어려운 것은 confidence 를 낮게(0.5 이하)."
    ),
}

SHELF_TOOL = {
    "name": "save_shelf_days",
    "description": "재료별 보통 보관 일수 저장",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "물어본 이름 그대로"},
                        "is_food": {"type": "boolean", "description": "먹는 식재료가 아니면 false"},
                        "category": {"type": "string", "description": "채소/과일/육류/해산물/유제품/가공식품/양념/곡류 등"},
                        "shelf_days": {"type": "integer", "description": "구입 직후 권장 보관법으로 보통 며칠 (1~730)"},
                        "storage": {"type": "string", "enum": ["fridge", "freezer", "room"]},
                    },
                    "required": ["name", "is_food", "shelf_days", "storage"],
                },
            }
        },
        "required": ["items"],
    },
}


def model_for(kind: Kind) -> str:
    return CLAUDE_MODEL if kind == "receipt" else CLAUDE_MODEL_SMART


def _tool_input(response, tool_name: str):
    if response.stop_reason == "refusal":
        raise IngestError("이 사진은 처리할 수 없어요. 다른 사진으로 해 주세요.")
    block = next((b for b in response.content if b.type == "tool_use" and b.name == tool_name), None)
    if block is None:
        raise IngestError("사진에서 재료를 읽지 못했어요. 다시 시도해 주세요.")
    return block.input


def extract_items(client, image_bytes: bytes, kind: Kind, catalog_names: list[str], today: date) -> list[DraftItem]:
    """사진 → 확인 표에 보여 줄 재료 목록. 실패하면 IngestError."""
    try:
        media_type, data = prepare_image(image_bytes)
    except Exception:
        raise IngestError("사진 파일을 열지 못했어요. JPG·PNG·WEBP 사진을 올려 주세요.")
    prompt = PROMPTS[kind] + "\n\n참고용 재료 이름 목록: " + ", ".join(catalog_names) + f"\n\n오늘은 {today.isoformat()} 이에요."
    try:
        response = client.messages.create(
            model=model_for(kind),
            max_tokens=4096,
            tools=[EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "save_ingredients"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except anthropic.RateLimitError:
        raise IngestError("요청이 많아 잠시 쉬어야 해요. 조금 뒤에 다시 해 주세요.")
    except anthropic.APIConnectionError:
        raise IngestError("Claude 에 연결하지 못했어요. 네트워크를 확인해 주세요.")
    except anthropic.APIStatusError as e:
        raise IngestError(f"Claude 호출이 실패했어요 (오류 {e.status_code}).")
    return parse_extraction(_tool_input(response, "save_ingredients"), today)


def estimate_shelf_days(client, names: list[str]) -> list[ShelfEstimate]:
    """카탈로그에 없는 재료들의 보관 일수를 Haiku 에게 한 번에 물어봐요. 실패하면 빈 목록."""
    if not names:
        return []
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            tools=[SHELF_TOOL],
            tool_choice={"type": "tool", "name": "save_shelf_days"},
            messages=[{"role": "user", "content": (
                "한국 가정 기준으로, 아래 식재료를 산 직후 권장 보관법(냉장·냉동·실온)으로 보관할 때 "
                "보통 며칠 가는지 알려 주세요. 보수적으로(짧게) 잡아요.\n" + "\n".join(f"- {n}" for n in names)
            )}],
        )
        return parse_shelf_estimates(_tool_input(response, "save_shelf_days"), names)
    except (anthropic.APIError, IngestError):
        return []


def add_to_catalog(estimates: list[ShelfEstimate]) -> None:
    """추정한 재료를 카탈로그에 추가 (모든 사용자 공용, 이미 있으면 건너뜀)."""
    if not estimates:
        return
    with transaction() as conn:
        for e in estimates:
            conn.execute(
                "insert into ingredient_catalog (name, category, default_shelf_days, storage)"
                " values (%s, %s, %s, %s) on conflict (name) do nothing",
                (e.name, e.category, e.shelf_days, e.storage),
            )
    _load_catalog_rows.clear()  # 카탈로그 캐시 비우기


def save_drafts(user_id: str, drafts: list[DraftItem], client=None) -> tuple[list[str], list[tuple[str, str]]]:
    """확인한 재료를 재고에 저장. (저장한 이름들, [(못 넣은 이름, 이유)])

    카탈로그에도 없고 유통기한도 없는 재료는 Claude 로 보관 일수를 추정해 카탈로그에 넣은 뒤 저장해요.
    """
    catalog = get_catalog()
    unknown = sorted({d.name for d in drafts if d.expires_at is None and match_catalog(d.name, catalog) is None})
    if unknown and client is not None:
        add_to_catalog(estimate_shelf_days(client, unknown))

    saved, failed = [], []
    for d in drafts:
        try:
            add_item(user_id, ItemInput(d.name, d.quantity, d.unit, d.purchased_at, d.expires_at))
            saved.append(d.name)
        except ValueError as e:
            failed.append((d.name, str(e)))
    return saved, failed
