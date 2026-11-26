"""알레르기 성분 사전 — 순수 함수 (Phase 3, 팀원 B).

레시피 재료 이름에 아래 낱말이 들어 있으면 그 알레르기 성분이 있다고 봐요.
- 기준: 식품 알레르기 표시 대상(달걀, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기,
  복숭아, 토마토, 호두, 닭고기, 쇠고기, 오징어, 조개류, 잣)
- 안전을 위해 **넓게** 잡아요. 애매하면 포함하는 쪽이에요 (예: 간장 → 대두·밀).
- preferences 의 allergy 값은 사용자가 말한 낱말이라 normalize_allergy() 로 이 이름에 맞춰요.
"""
from __future__ import annotations

from typing import Iterable, Optional

# 알레르기 이름 → 재료 이름에 들어 있으면 해당하는 낱말
ALLERGEN_KEYWORDS: dict[str, list[str]] = {
    "달걀": ["달걀", "계란", "메추리알", "노른자", "흰자", "마요네즈"],
    "우유": ["우유", "생크림", "휘핑크림", "버터", "치즈", "요거트", "요구르트", "요플레", "연유", "분유", "파르메산"],
    "메밀": ["메밀"],
    "땅콩": ["땅콩"],
    "대두": ["대두", "두부", "두유", "된장", "간장", "고추장", "쌈장", "춘장", "청국장", "유부", "미소", "콩"],
    "밀": ["밀가루", "부침가루", "튀김가루", "빵가루", "빵", "국수", "소면", "칼국수", "파스타", "스파게티",
          "마카로니", "만두피", "또띠아", "통밀", "간장", "고추장", "쌈장", "춘장"],
    "고등어": ["고등어"],
    "게": ["게살", "꽃게", "대게", "킹크랩", "크래미", "크래비"],
    "새우": ["새우"],
    "돼지고기": ["돼지", "삼겹", "목살", "햄", "베이컨", "소시지"],
    "복숭아": ["복숭아"],
    "토마토": ["토마토"],
    "호두": ["호두"],
    "닭고기": ["닭", "치킨"],
    "쇠고기": ["쇠고기", "소고기", "우둔", "차돌", "사골", "양지"],
    "오징어": ["오징어"],
    "조개류": ["조개", "바지락", "홍합", "굴", "전복", "가리비", "재첩", "꼬막", "키조개"],
    "잣": ["잣"],
}

# 사용자가 말하는 다른 이름 → 위 알레르기 이름
_ALLERGY_ALIASES: dict[str, str] = {
    "계란": "달걀", "알류": "달걀", "난류": "달걀",
    "유제품": "우유",
    "콩": "대두",
    "밀가루": "밀", "글루텐": "밀",
    "소고기": "쇠고기",
    "돼지": "돼지고기",
    "닭": "닭고기",
    "갑각류": "새우",  # 갑각류는 새우·게 둘 다 → find 할 때 함께 처리
    "조개": "조개류", "굴": "조개류", "홍합": "조개류", "전복": "조개류", "바지락": "조개류",
}


# 낱말을 찾기 전에 지울 것 (예: '땅콩'의 '콩'을 대두로 보지 않기)
_IGNORE_BEFORE_MATCH: dict[str, list[str]] = {
    "대두": ["땅콩"],
}


def find_allergens(ingredient_names: Iterable[str]) -> list[str]:
    """재료 이름 목록 → 들어 있는 알레르기 이름 목록 (ALLERGEN_KEYWORDS 순서)."""
    names = [n.replace(" ", "") for n in ingredient_names if n]
    found = []
    for allergen, words in ALLERGEN_KEYWORDS.items():
        ignore = _IGNORE_BEFORE_MATCH.get(allergen, [])
        for name in names:
            for x in ignore:
                name = name.replace(x, "")
            if any(w in name for w in words):
                found.append(allergen)
                break
    return found


def normalize_allergy(word: str) -> list[str]:
    """사용자가 말한 알레르기 낱말 → 레시피의 allergens 값과 비교할 이름 목록.

    예: '계란' → ['달걀'], '갑각류' → ['새우', '게'], '땅콩' → ['땅콩'].
    사전에 없는 낱말은 그대로 돌려줘요 (예: '키위' → ['키위']).
    """
    w = word.strip().replace(" ", "")
    if not w:
        return []
    if w == "갑각류":
        return ["새우", "게"]
    if w in ALLERGEN_KEYWORDS:
        return [w]
    alias: Optional[str] = _ALLERGY_ALIASES.get(w)
    return [alias] if alias else [w]
