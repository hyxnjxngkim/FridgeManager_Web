"""냉장고 에이전트 (Phase 4) — Claude + 도구 7개, 직접 쓴 도구 반복(manual loop) + 스트리밍.

화면(views/chat.py)은 run_turn() 이 내보내는 글자를 그대로 st.write_stream 으로 보여줘요.
재고를 실제로 빼는 일은 에이전트가 하지 않아요: prepare_cooking 은 '미리보기'만 만들고,
사용자가 화면에서 확인 버튼을 눌러야 lib/cooking.apply_cook 이 실행돼요.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

import anthropic

from lib.config import CLAUDE_MODEL
from lib.cooking_rules import CookPlan, plan_cook, summarize_plan
from lib.dates import today_kst
from lib.inventory import days_left, get_catalog, get_expiring, get_inventory
from lib.models import RecipeMatch
from lib.preferences import KIND_LABELS, delete_preference, get_preferences, save_preference
from lib.recipe_source import search_recipes

MAX_STEPS = 6  # 한 번 물어볼 때 도구를 부르는 최대 횟수
MAX_TOKENS = 4096

SYSTEM_PROMPT = """너는 '냉장고를 부탁해' 앱의 요리 도우미야. 사용자의 냉장고 재고를 보고, 유통기한이 임박한 재료부터 쓰는 요리를 추천해.

규칙
- 무엇을 만들지 추천할 때는 먼저 get_expiring 으로 임박 재료를 확인하고, 그 재료로 search_recipes 를 불러.
- 레시피는 search_recipes 결과에 있는 것만 추천해. 결과에 없는 레시피를 지어내지 마. 결과가 없으면 솔직히 말해.
- 추천한 레시피는 화면에 카드로 따로 보여지니, 답변에서는 왜 추천하는지(어떤 임박 재료를 구하는지)와 없는 재료의 대체재만 짧게 말해.
- 사용자가 알레르기·좋아하는 맛·싫어하는 재료·식단 목표를 말하면 save_preference 로 저장하고, 저장했다고 알려줘. 취소하면 delete_preference.
- 알레르기 재료가 들어간 레시피는 절대 추천하지 마.
- 사용자가 "이거 만들게"처럼 요리하겠다고 하면 prepare_cooking 을 불러. 이건 재고 빼기 '미리보기'만 만들어. 실제로 빼려면 사용자가 화면에서 확인해야 한다고 알려줘. 재고가 이미 빠졌다고 말하지 마.
- 한국어 존댓말(해요체)로만, 짧고 친근하게 답해. 반말을 섞지 마. 목록은 3개 이하로.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_inventory",
        "description": "사용자의 현재 냉장고 재고 전체 (이름, 수량, 단위, 유통기한, 남은 일수).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_expiring",
        "description": "오늘부터 days 일 안에 유통기한이 끝나는 재료. 추천 전에 먼저 확인해.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 0, "maximum": 14, "description": "기본 3"}},
        },
    },
    {
        "name": "search_recipes",
        "description": "재료 이름으로 레시피 검색. 알레르기 재료가 든 레시피는 자동으로 빠져. 결과의 id 는 prepare_cooking 에 써.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredients": {"type": "array", "items": {"type": "string"}, "description": "우선 쓰고 싶은 재료 (보통 임박 재료)"},
                "max_minutes": {"type": "integer", "description": "바쁠 때 최대 조리 시간(분)"},
                "servings": {"type": "integer", "description": "인원수"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "예: 고단백, 다이어트, 매운맛"},
            },
            "required": ["ingredients"],
        },
    },
    {
        "name": "get_preferences",
        "description": "저장된 취향·알레르기·식단 목표 목록.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_preference",
        "description": "취향·알레르기를 기억. kind: allergy(알레르기) / like(좋아함) / dislike(싫어함) / diet(식단 목표). value 는 재료나 맛 이름 하나.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(KIND_LABELS)},
                "value": {"type": "string", "description": "예: 땅콩, 매운맛, 다이어트"},
            },
            "required": ["kind", "value"],
        },
    },
    {
        "name": "delete_preference",
        "description": "저장된 취향·알레르기를 지움 (사용자가 취소하거나 바뀌었다고 할 때).",
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": list(KIND_LABELS)}, "value": {"type": "string"}},
            "required": ["kind", "value"],
        },
    },
    {
        "name": "prepare_cooking",
        "description": "사용자가 레시피를 만들겠다고 할 때 재고 빼기 미리보기를 만듦. 실제 재고는 사용자가 화면에서 확인해야 빠져. recipe_id 는 이번 대화의 search_recipes 결과에서.",
        "input_schema": {
            "type": "object",
            "properties": {"recipe_id": {"type": "string"}, "servings": {"type": "integer", "minimum": 1, "maximum": 20}},
            "required": ["recipe_id"],
        },
    },
]


@dataclass
class AgentState:
    """한 사용자의 채팅 상태 (Streamlit session_state 에 보관)."""

    messages: list[Any] = field(default_factory=list)  # Claude API 대화 기록
    recipes: dict[str, RecipeMatch] = field(default_factory=dict)  # 이번 대화에서 찾은 레시피
    shown_matches: list[RecipeMatch] = field(default_factory=list)  # 이번 답변에 카드로 보여줄 것
    pending_cook: Optional[CookPlan] = None  # 화면에서 확인을 기다리는 재고 빼기
    notes: list[str] = field(default_factory=list)  # 다음 질문 때 Claude 에게 알려줄 앱 소식
    tools_used: list[str] = field(default_factory=list)


class ToolError(Exception):
    pass


def _match_summary(m: RecipeMatch) -> dict:
    r = m.recipe
    return {
        "id": r.id,
        "title": r.title,
        "cook_minutes": r.cook_minutes,
        "servings": r.servings,
        "uses_expiring": m.uses_expiring,
        "missing": m.missing,
        "ingredients": [f"{i.name} {i.qty:g}{i.unit or ''}" if i.qty else i.name for i in r.ingredients],
        "tags": r.tags,
    }


def _int(value: Any, default: Optional[int], lo: int, hi: int) -> Optional[int]:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError("숫자가 아니에요.")
    return max(lo, min(hi, int(value)))


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ToolError("문자열 목록이어야 해요.")
    return [x.strip() for x in value if x.strip()][:20]


def make_tool_handlers(user_id: str, state: AgentState) -> dict[str, Callable[[dict], Any]]:
    """도구 이름 → 실행 함수. 모든 도구는 이 user_id 의 데이터만 다뤄요."""
    today = today_kst()

    def item_view(i):
        return {"name": i.name, "quantity": i.quantity, "unit": i.unit, "expires_at": i.expires_at.isoformat(),
                "days_left": days_left(i, today)}

    def t_get_inventory(_: dict):
        return [item_view(i) for i in get_inventory(user_id)]

    def t_get_expiring(args: dict):
        days = _int(args.get("days"), 3, 0, 14)
        return [item_view(i) for i in get_expiring(user_id, days)]

    def t_search_recipes(args: dict):
        ingredients = _str_list(args.get("ingredients"))
        tags = _str_list(args["tags"]) if args.get("tags") is not None else None
        matches = search_recipes(
            user_id,
            ingredients,
            max_minutes=_int(args.get("max_minutes"), None, 1, 600),
            servings=_int(args.get("servings"), None, 1, 20),
            tags=tags,
        )
        for m in matches:
            state.recipes[m.recipe.id] = m
        state.shown_matches = matches[:3]
        return [_match_summary(m) for m in matches[:3]]

    def t_get_preferences(_: dict):
        return [{"kind": p.kind, "label": KIND_LABELS[p.kind], "value": p.value} for p in get_preferences(user_id)]

    def t_save_preference(args: dict):
        try:
            p = save_preference(user_id, str(args.get("kind", "")), str(args.get("value", "")))
        except ValueError as e:
            raise ToolError(str(e))
        return {"saved": True, "kind": p.kind, "value": p.value}

    def t_delete_preference(args: dict):
        try:
            ok = delete_preference(user_id, str(args.get("kind", "")), str(args.get("value", "")))
        except ValueError as e:
            raise ToolError(str(e))
        return {"deleted": ok}

    def t_prepare_cooking(args: dict):
        recipe_id = args.get("recipe_id")
        if not isinstance(recipe_id, str) or recipe_id not in state.recipes:
            raise ToolError("이번 대화의 search_recipes 결과에 있는 recipe_id 를 써 주세요.")
        recipe = state.recipes[recipe_id].recipe
        plan = plan_cook(recipe, get_inventory(user_id), get_catalog(), today,
                         servings=_int(args.get("servings"), None, 1, 20))
        state.pending_cook = plan
        return summarize_plan(plan)

    return {
        "get_inventory": t_get_inventory,
        "get_expiring": t_get_expiring,
        "search_recipes": t_search_recipes,
        "get_preferences": t_get_preferences,
        "save_preference": t_save_preference,
        "delete_preference": t_delete_preference,
        "prepare_cooking": t_prepare_cooking,
    }


def run_tool(handlers: dict[str, Callable[[dict], Any]], block) -> dict:
    """tool_use 블록 하나를 실행해 tool_result 를 만들어요. 실패는 is_error 로 돌려줘요."""
    handler = handlers.get(block.name)
    args = block.input if isinstance(block.input, dict) else None
    try:
        if handler is None:
            raise ToolError(f"없는 도구예요: {block.name}")
        if args is None:
            raise ToolError("입력 형식이 올바르지 않아요.")
        result = handler(args)
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        return {"type": "tool_result", "tool_use_id": block.id, "content": content}
    except ToolError as e:
        return {"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True}
    except Exception as e:  # DB 오류 등 — 에이전트가 사용자에게 설명할 수 있게
        return {"type": "tool_result", "tool_use_id": block.id, "content": f"도구 실행 중 오류: {type(e).__name__}", "is_error": True}


def run_turn(
    client,
    state: AgentState,
    user_id: str,
    user_text: str,
    model: str = CLAUDE_MODEL,
) -> Iterator[str]:
    """사용자 메시지 하나를 처리하며 답변 글자를 조금씩 내보내요 (st.write_stream 용)."""
    start = len(state.messages)
    state.shown_matches = []
    state.tools_used = []
    handlers = make_tool_handlers(user_id, state)

    context = f"(오늘 날짜: {today_kst().isoformat()})"
    if state.notes:
        context += " 앱 알림: " + " / ".join(state.notes)
        state.notes = []
    state.messages.append({"role": "user", "content": [{"type": "text", "text": context}, {"type": "text", "text": user_text}]})

    try:
        for step in range(MAX_STEPS):
            with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=state.messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
                response = stream.get_final_message()

            if response.stop_reason == "refusal":
                del state.messages[start:]
                yield "\n\n죄송해요, 이 요청은 도와드리기 어려워요."
                return

            state.messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return
            if response.stop_reason == "max_tokens":
                yield "\n\n(답변이 너무 길어 중간에 멈췄어요. 다시 물어봐 주세요.)"
                del state.messages[start:]
                return

            state.tools_used += [b.name for b in tool_uses]
            results = [run_tool(handlers, b) for b in tool_uses]  # 결과는 한 메시지에 모아서
            state.messages.append({"role": "user", "content": results})
            yield "\n\n"
        yield "(도구를 너무 많이 불러서 여기서 멈췄어요.)"
    except anthropic.RateLimitError:
        del state.messages[start:]
        yield "\n\n요청이 많아 잠시 쉬어야 해요. 조금 뒤에 다시 물어봐 주세요."
    except anthropic.APIConnectionError:
        del state.messages[start:]
        yield "\n\nClaude 에 연결하지 못했어요. 네트워크를 확인해 주세요."
    except anthropic.APIStatusError as e:
        del state.messages[start:]
        yield f"\n\nClaude 호출이 실패했어요 (오류 {e.status_code})."
