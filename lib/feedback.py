"""피드백 학습 ② — 요리 후 👍/👎·코멘트 저장, 코멘트를 취향으로 바꾸기.

- 평점은 meal_logs.rating (👍=1, 👎=-1), 코멘트는 meal_logs.feedback 에 저장해요.
- 코멘트가 있을 때만 Claude(Haiku 4.5)에게 취향으로 바꿔 달라고 해요 (비용 절약).
  예: "너무 매웠어" → dislike 매운맛.  결과는 preferences 에 strength 를 올려 저장해요.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import anthropic

from lib.config import CLAUDE_MODEL
from lib.db import execute, fetch_all, fetch_one
from lib.dates import today_kst
from lib.personalize import RecipeHistory
from lib.preferences import KIND_LABELS, MAX_VALUE_LENGTH, bump_preference

MAX_COMMENT = 200
LEARN_KINDS = ["like", "dislike", "diet", "allergy"]

EXTRACT_SYSTEM = (
    "사용자가 요리를 먹고 남긴 한 줄 후기에서 앞으로 레시피 추천에 반영할 취향만 뽑아. "
    "kind: like(좋아하는 맛·재료), dislike(싫어하는 맛·재료), diet(식단 목표), "
    "allergy(사용자가 알레르기·두드러기라고 분명히 말한 재료만). "
    "value 는 '매운맛', '짠맛', '오이'처럼 짧은 단어 하나. 확실하지 않으면 넣지 마. 반영할 게 없으면 빈 목록."
)
EXTRACT_TOOL = {
    "name": "save_taste_changes",
    "description": "후기에서 뽑은 취향 변화를 저장",
    "input_schema": {
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": LEARN_KINDS},
                        "value": {"type": "string"},
                    },
                    "required": ["kind", "value"],
                },
            }
        },
        "required": ["changes"],
    },
}


@dataclass
class UnratedMeal:
    id: str
    title: str
    day: date


def record_feedback(user_id: str, meal_log_id: str, rating: int, comment: Optional[str] = None) -> None:
    if rating not in (1, -1):
        raise ValueError("평가는 👍 또는 👎 로 해 주세요.")
    comment = (comment or "").strip()[:MAX_COMMENT] or None
    execute(
        "update meal_logs set rating = %s, feedback = %s where id = %s and user_id = %s",
        (rating, comment, meal_log_id, user_id),
    )


def parse_changes(tool_input) -> list[tuple[str, str]]:
    """Claude 도구 입력을 검사해 (kind, value) 목록으로. 이상한 값은 버려요."""
    out: list[tuple[str, str]] = []
    changes = tool_input.get("changes") if isinstance(tool_input, dict) else None
    if not isinstance(changes, list):
        return out
    for c in changes[:3]:
        if not isinstance(c, dict):
            continue
        kind, value = c.get("kind"), c.get("value")
        if kind in LEARN_KINDS and isinstance(value, str) and 0 < len(value.strip()) <= MAX_VALUE_LENGTH:
            out.append((kind, value.strip()))
    return out


def extract_taste_changes(client, recipe_title: str, rating: int, comment: str) -> list[tuple[str, str]]:
    """Haiku 4.5 로 후기 → 취향 변화. 실패하면 빈 목록 (평가 저장은 이미 끝났으니 조용히 넘어가요)."""
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=EXTRACT_SYSTEM,
            tools=[EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "save_taste_changes"},
            messages=[{"role": "user", "content": f"요리: {recipe_title}\n평가: {'👍' if rating > 0 else '👎'}\n후기: {comment}"}],
        )
    except anthropic.APIError:
        return []
    block = next((b for b in response.content if b.type == "tool_use"), None)
    return parse_changes(block.input) if block else []


def learn_from_comment(client, user_id: str, recipe_title: str, rating: int, comment: Optional[str]) -> list[str]:
    """코멘트가 있으면 취향을 배워 저장하고, 저장한 것의 설명 목록을 돌려줘요."""
    comment = (comment or "").strip()
    if not comment or client is None:
        return []
    saved = []
    for kind, value in extract_taste_changes(client, recipe_title, rating, comment[:MAX_COMMENT]):
        p = bump_preference(user_id, kind, value)
        saved.append(f"{KIND_LABELS[p.kind]}: {p.value}")
    return saved


def unrated_meals(user_id: str, days: int = 14) -> list[UnratedMeal]:
    since = today_kst() - timedelta(days=days)
    rows = fetch_all(
        "select id, recipe_title, (cooked_at at time zone 'Asia/Seoul')::date as day from meal_logs"
        " where user_id = %s and rating is null and recipe_title is not null"
        " and (cooked_at at time zone 'Asia/Seoul')::date >= %s order by cooked_at desc limit 10",
        (user_id, since),
    )
    return [UnratedMeal(str(r["id"]), r["recipe_title"], r["day"]) for r in rows]


def latest_meal_id(user_id: str, recipe_title: str, days: int = 14) -> Optional[str]:
    """에이전트용: 최근 days 일 안에 만든 그 요리의 가장 최근 기록."""
    row = fetch_one(
        "select id from meal_logs where user_id = %s and recipe_title = %s"
        " and cooked_at >= now() - make_interval(days => %s) order by cooked_at desc limit 1",
        (user_id, recipe_title, days),
    )
    return str(row["id"]) if row else None


def recipe_history(user_id: str) -> dict[str, RecipeHistory]:
    """레시피 이름별 평균 평점과 마지막으로 먹은 날 (개인화 점수용)."""
    rows = fetch_all(
        "select recipe_title as title, avg(rating)::float as avg_rating,"
        "       max((cooked_at at time zone 'Asia/Seoul')::date) as last_cooked"
        " from meal_logs where user_id = %s and recipe_title is not null group by recipe_title",
        (user_id,),
    )
    return {r["title"]: RecipeHistory(r["avg_rating"], r["last_cooked"]) for r in rows}
