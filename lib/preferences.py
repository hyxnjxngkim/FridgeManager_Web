"""취향·알레르기 기억 (preferences 테이블). 모든 함수는 user_id 의 데이터만 다뤄요.

저장 형식 (PLAN.md 11-2 약속): kind 는 allergy / like / dislike / diet, value 는 재료·맛 이름 하나.
"""
from __future__ import annotations

import re

from lib.db import execute, fetch_all, fetch_one
from lib.models import Preference

KIND_LABELS = {"allergy": "알레르기", "like": "좋아함", "dislike": "싫어함", "diet": "식단 목표"}
MAX_VALUE_LENGTH = 30


def normalize_value(value: str) -> str:
    """앞뒤 공백·여러 칸 공백 정리. 잘못된 값이면 ValueError."""
    value = re.sub(r"\s+", " ", (value or "")).strip()
    if not value:
        raise ValueError("내용이 비어 있어요.")
    if len(value) > MAX_VALUE_LENGTH:
        raise ValueError(f"너무 길어요 ({MAX_VALUE_LENGTH}자 이하).")
    return value


def check_kind(kind: str) -> str:
    if kind not in KIND_LABELS:
        raise ValueError(f"종류는 {', '.join(KIND_LABELS)} 중 하나여야 해요.")
    return kind


def _to_pref(row: dict) -> Preference:
    return Preference(id=str(row["id"]), kind=row["kind"], value=row["value"], strength=row["strength"])


def get_preferences(user_id: str) -> list[Preference]:
    rows = fetch_all(
        "select id, kind, value, strength from preferences where user_id = %s order by kind, created_at",
        (user_id,),
    )
    return [_to_pref(r) for r in rows]


def get_allergies(user_id: str) -> list[str]:
    return [p.value for p in get_preferences(user_id) if p.kind == "allergy"]


def save_preference(user_id: str, kind: str, value: str) -> Preference:
    """같은 (kind, value)가 이미 있으면 그대로 둬요. 잘못된 입력이면 ValueError."""
    kind, value = check_kind(kind), normalize_value(value)
    row = fetch_one(
        "insert into preferences (user_id, kind, value) values (%s, %s, %s)"
        " on conflict (user_id, kind, value) do update set value = excluded.value"
        " returning id, kind, value, strength",
        (user_id, kind, value),
    )
    return _to_pref(row)


def delete_preference(user_id: str, kind: str, value: str) -> bool:
    """지웠으면 True."""
    kind, value = check_kind(kind), normalize_value(value)
    return execute(
        "delete from preferences where user_id = %s and kind = %s and value = %s",
        (user_id, kind, value),
    ) > 0


def delete_preference_by_id(user_id: str, pref_id: str) -> None:
    execute("delete from preferences where id = %s and user_id = %s", (pref_id, user_id))


def bump_preference(user_id: str, kind: str, value: str) -> Preference:
    """피드백 학습용: 없으면 새로, 있으면 strength(강도)를 1 올려요."""
    kind, value = check_kind(kind), normalize_value(value)
    row = fetch_one(
        "insert into preferences (user_id, kind, value) values (%s, %s, %s)"
        " on conflict (user_id, kind, value) do update set strength = preferences.strength + 1"
        " returning id, kind, value, strength",
        (user_id, kind, value),
    )
    return _to_pref(row)
