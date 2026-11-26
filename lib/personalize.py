"""피드백 학습 ① — 추천 순서 개인화 (순수 함수). 모델 재학습이 아니라 내 기록으로 점수를 조정해요.

검색 점수(B의 search_recipes)에 더하고 빼요.
- 👍 받은 레시피 +2 × 평균,  👎 받은 레시피 −3
- 최근 7일 안에 먹은 레시피 −2 (같은 요리 연속 추천 줄이기)
- 싫어하는 재료·태그가 들어 있으면 −3 × strength
- 좋아하는 재료·태그나 식단 목표 태그가 있으면 +1 × strength (최대 +3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from typing import Optional

from lib.models import Preference, RecipeMatch

LIKE_WEIGHT, DISLIKE_WEIGHT = 2.0, 3.0
RECENT_DAYS, RECENT_PENALTY = 7, 2.0
PREF_DISLIKE, PREF_LIKE, PREF_LIKE_CAP = 3.0, 1.0, 3.0


@dataclass
class RecipeHistory:
    avg_rating: Optional[float]  # 👍=1, 👎=-1 의 평균 (평가 없으면 None)
    last_cooked: Optional[date]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _mentions(match: RecipeMatch, value: str) -> bool:
    key = _norm(value)
    if len(key) < 1:
        return False
    r = match.recipe
    words = [_norm(t) for t in r.tags] + [_norm(i.name) for i in r.ingredients] + [_norm(r.title)]
    return any(key == w or (len(key) >= 2 and key in w) for w in words)


def personal_bonus(match: RecipeMatch, history: dict[str, RecipeHistory], prefs: list[Preference], today: date) -> float:
    bonus = 0.0
    h = history.get(match.recipe.title)
    if h:
        if h.avg_rating is not None:
            bonus += h.avg_rating * LIKE_WEIGHT if h.avg_rating > 0 else -DISLIKE_WEIGHT
        if h.last_cooked and (today - h.last_cooked).days < RECENT_DAYS:
            bonus -= RECENT_PENALTY
    like = 0.0
    for p in prefs:
        if p.kind == "dislike" and _mentions(match, p.value):
            bonus -= PREF_DISLIKE * max(p.strength, 1)
        elif p.kind in ("like", "diet") and _mentions(match, p.value):
            like += PREF_LIKE * max(p.strength, 1)
    return bonus + min(like, PREF_LIKE_CAP)


def personalize(
    matches: list[RecipeMatch], history: dict[str, RecipeHistory], prefs: list[Preference], today: date
) -> list[RecipeMatch]:
    """점수를 조정해 다시 정렬. 원래 RecipeMatch 는 바꾸지 않고 새로 만들어요."""
    adjusted = [replace(m, score=round(m.score + personal_bonus(m, history, prefs, today), 2)) for m in matches]
    return sorted(adjusted, key=lambda m: (-m.score, m.recipe.title))
