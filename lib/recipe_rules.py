"""레시피 추천 점수 — 순수 함수 (Phase 3, 팀원 B).

점수 (PLAN 5장 ③-3)
    임박 재료 사용 수 × 3 + 보유 재료 비율 × 2 + 취향 태그 일치 수 × 1   (+ 평점 보정은 Phase 6)

재료 이름 맞추기
    1) 카탈로그 이름·별칭으로 통일 ('파' → '대파', '다진 마늘' → '다진마늘')
    2) 띄어쓰기를 없애고, 같거나 한쪽이 다른 쪽의 **끝**에 붙어 있으면 같은 재료
       ('두부' ↔ '연두부'·'순두부', '새우' ↔ '칵테일새우', '대파' ↔ '다진대파')
       끝만 보는 이유: '고추' ↔ '고추장', '파' ↔ '파프리카' 처럼 앞이 같은 다른 재료를 막으려고
    3) 단, 끝이 같아도 다른 재료인 쌍(NOT_SAME)은 같은 재료로 보지 않음 ('배추' ≠ '양배추')
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from lib.catalog import match_catalog
from lib.models import CatalogItem, Recipe, RecipeMatch

EXPIRING_WEIGHT = 3.0
HAVE_RATIO_WEIGHT = 2.0
TAG_WEIGHT = 1.0

# 바쁜 날(일정 kind = busy) 조리 시간 상한. PLAN 은 10분이지만 추정 시간으로는 10분 이하가
# 16개뿐이라 15분으로 올림 (팀 결정, PLAN.md 반영은 A)
BUSY_MAX_MINUTES = 15

# 집에 늘 있다고 보는 양념 — 보유 비율·없는 재료 계산에서 빼요
PANTRY = {
    "물", "소금", "설탕", "후추", "후춧가루", "통후추", "식용유", "올리브유", "올리브오일", "참기름",
    "들기름", "식초", "간장", "저염간장", "국간장", "진간장", "맛술", "청주", "깨", "참깨", "통깨",
    "다진마늘", "올리고당", "물엿", "꿀",
}


# 끝 글자가 같아도 다른 재료인 쌍 (짧은 이름, 긴 이름) — 띄어쓰기 없이.
# 레시피 데이터 1,151개에서 '끝이 같은 이름 쌍'을 모두 뽑아 보고 실제로 다른 재료만 골랐어요.
# 새로 발견되면 한 줄씩 더해요. (알배추·얼갈이배추 = 배추, 건새우 = 새우 처럼 같은 재료는 넣지 않아요)
NOT_SAME = {
    ("배추", "양배추"),
    ("배추", "적양배추"),
    ("상추", "양상추"),
    ("버터", "땅콩버터"),
    ("두유", "대두유"),  # 대두유 = 콩기름
    ("밀가루", "메밀가루"),
    ("포도", "건포도"),
    ("이스트", "토마토페이스트"),
}


def _key(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def canonical(name: str, catalog: Optional[list[CatalogItem]] = None) -> str:
    """카탈로그 기준 이름 (없으면 띄어쓰기만 없앤 이름)."""
    if catalog:
        item = match_catalog(name, catalog)
        if item:
            return _key(item.name)
    return _key(name)


def _same_key(ka: str, kb: str) -> bool:
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    return len(short) >= 2 and long_.endswith(short) and (short, long_) not in NOT_SAME


def same_ingredient(a: str, b: str, catalog: Optional[list[CatalogItem]] = None) -> bool:
    return _same_key(canonical(a, catalog), canonical(b, catalog))


def is_pantry(name: str, catalog: Optional[list[CatalogItem]] = None) -> bool:
    return canonical(name, catalog) in PANTRY or _key(name) in PANTRY


def score_recipe(
    recipe: Recipe,
    expiring: Iterable[str],
    have: Iterable[str],
    wanted_tags: Iterable[str] = (),
    catalog: Optional[list[CatalogItem]] = None,
) -> RecipeMatch:
    """레시피 하나의 점수와 구출 재료·없는 재료.

    - expiring: 임박 재료 이름 (search_recipes 의 ingredients)
    - have: 재고에 있는 재료 이름 전체 (임박 재료 포함)
    - uses_expiring: expiring 중 이 레시피가 쓰는 것 (입력 순서 유지)
    - missing: 레시피의 필수 재료 중 재고에 없는 것 (선택 재료·양념 제외)
    """
    expiring, have = list(expiring), list(have)
    key = {n: canonical(n, catalog) for n in [*expiring, *have, *(i.name for i in recipe.ingredients)]}
    needed = [i for i in recipe.ingredients if not i.optional and not is_pantry(i.name, catalog)]
    have_keys = [key[h] for h in [*have, *expiring]]

    uses = [e for e in expiring if any(_same_key(key[e], key[i.name]) for i in recipe.ingredients)]
    owned = [i for i in needed if any(_same_key(h, key[i.name]) for h in have_keys)]
    missing = [i.name for i in needed if i not in owned]
    have_ratio = len(owned) / len(needed) if needed else 1.0
    tag_hits = len(set(wanted_tags) & set(recipe.tags))

    score = len(uses) * EXPIRING_WEIGHT + have_ratio * HAVE_RATIO_WEIGHT + tag_hits * TAG_WEIGHT
    return RecipeMatch(recipe=recipe, score=round(score, 4), uses_expiring=uses, missing=missing)


def rank(matches: Iterable[RecipeMatch]) -> list[RecipeMatch]:
    """점수 높은 순, 같으면 구출 재료 많은 순, 없는 재료 적은 순, 제목 순."""
    return sorted(matches, key=lambda m: (-m.score, -len(m.uses_expiring), len(m.missing), m.recipe.title))


def has_allergen(recipe: Recipe, allergies: Iterable[str]) -> bool:
    """SQL 로 이미 걸러도, 화면에 보이기 전에 한 번 더 확인할 때 써요."""
    return bool(set(recipe.allergens) & set(allergies))
