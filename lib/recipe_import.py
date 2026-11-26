"""식품안전나라 레시피(COOKRCP01) 한 줄 → Recipe 로 바꾸기 — 순수 함수 (Phase 3, 팀원 B).

DB·네트워크·Streamlit 없이 돌아가요. scripts/seed_recipes.py 가 API 응답을 이 함수로 바꿔 저장해요.

변환 규칙 (팀원 B 결정)
- id          : 'foodsafety:<RCP_SEQ>'. DB 에는 recipes.source_id 로 저장 (upsert 기준)
- 재료        : RCP_PARTS_DTLS 를 파싱. 소제목(●양념장 :, [소스], 고명 …)은 빼고, 고명·장식·곁들임은 optional
- 조리 순서   : MANUAL01~20 을 이어 붙이고 번호를 다시 매김. 끝에 붙은 a·b·c 같은 찌꺼기 글자는 지움
- cook_minutes: 코드로 추정 (조리법 기본 시간 + 단계 수, 조리 순서에 'N분'이 있으면 그 합도 참고). 화면엔 "추정"
- servings    : 1 (이 데이터는 1인분 기준)
- tags        : 종류(RCP_PAT2), 조리법(RCP_WAY2), 해시태그 + 고단백(단백질 ≥ 15g), 다이어트(≤ 150kcal), 매운맛
- allergens   : lib/allergens.py 사전으로 재료 이름에서 찾음
- image_url   : ATT_FILE_NO_MAIN 을 https 로
- 출처        : 레시피별로 넣지 않음 (앱 전체에 "레시피 데이터: 식품안전나라" 한 줄)
"""
from __future__ import annotations

import re
from typing import Optional

from lib.allergens import find_allergens
from lib.models import Recipe, RecipeIngredient

SOURCE_PREFIX = "foodsafety:"
SERVINGS = 1
HIGH_PROTEIN_G = 15.0  # 이 이상이면 '고단백' (전체 레시피의 위쪽 약 25%)
DIET_KCAL = 150.0  # 이 이하이면 '다이어트'
SPICY_WORDS = ["고춧가루", "고추장", "청양고추", "페퍼론치노", "핫소스", "칠리", "고추기름"]

# 조리법별 기본 시간(분) — 추정용
WAY_BASE_MINUTES = {"기타": 10, "볶기": 15, "굽기": 20, "찌기": 20, "끓이기": 25, "튀기기": 25}

_OPTIONAL_SECTIONS = ("고명", "장식", "곁들", "토핑", "토 핑", "가니쉬", "데코")
_VAGUE_QTY = ("약간", "적당량", "적량", "조금", "소량", "한꼬집", "한 꼬집", "기호에 따라")
# 이름 앞에 붙어 나오는 소제목 낱말 (예: '양념 들깻가루', '육수 사골육수', '저염간장양념 저염간장')
_LEADING_HEADER = re.compile(
    r"^(?:주재료|부재료|재료|고명|장식|곁들임|완자|\S*(?:양념장?|소스|드레싱|육수))\s+(?=\S)"
)

_UNITS = sorted(
    ["kg", "g", "ml", "mL", "L", "cc", "개", "큰술", "작은술", "Ts", "ts", "T", "t", "스푼", "컵", "장",
     "쪽", "알", "마리", "줄기", "모", "봉지", "봉", "단", "줌", "톨", "뿌리", "송이", "포기", "통", "cm"],
    key=len,
    reverse=True,
)
_UNIT_ALT = "|".join(re.escape(u) for u in _UNITS)
# 수량: '75g', '1/2개', '2~3개'(앞 숫자), '1.5큰술'
_QTY = re.compile(rf"(\d+(?:\.\d+)?)(?:\s*/\s*(\d+))?(?:\s*[~∼]\s*\d+(?:\.\d+)?)?\s*({_UNIT_ALT})?")
_FRACTION_VALUE = {"½": 0.5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 0.25, "¾": 0.75, "⅛": 0.125}
# 줄 안의 소제목: '양념장 :', '주재료 >', '저나트륨 간장소스:'
_SECTION = re.compile(r"[●·•▶■□◆\-]*\s*([가-힣A-Za-z][가-힣A-Za-z ]{0,14}?)\s*[:>]")
_UNICODE_FRACTIONS = "½⅓⅔¼¾⅛"


# ── 재료 ───────────────────────────────────────────
def _is_optional_section(label: str) -> bool:
    return any(w in label for w in _OPTIONAL_SECTIONS)


def _is_header_line(line: str) -> bool:
    """쉼표·숫자·'약간' 같은 양 표현이 없는 짧은 줄 = 소제목 (예: '새우두부계란찜', '고명', '두유 소스')."""
    if "," in line or re.search(r"\d", line) or any(v in line for v in _VAGUE_QTY):
        return False
    return len(line) <= 20


def _split_top_level(text: str) -> list[str]:
    """괄호 밖의 쉼표로만 나누기 (예: '닭고기(가슴살, 30g), 쌀(50g)' → 2개)."""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in "(（[":
            depth += 1
        elif ch in ")）]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def clean_name(name: str) -> str:
    for v in _VAGUE_QTY:
        name = name.replace(v, " ")
    for f in _UNICODE_FRACTIONS:
        name = name.replace(f, "")
    name = re.sub(r"\s+", " ", name).strip(" .,:;·•●-~")
    name = _LEADING_HEADER.sub("", name)
    if "재료 " in name:  # '고기 삶는 재료 양파' → '양파'
        name = name.rsplit("재료 ", 1)[1]
    return name.strip()


def _fractions_to_decimal(text: str) -> str:
    """'1½컵' → '1.5컵', '½개' → '0.5개'"""
    def repl(m: re.Match) -> str:
        whole = float(m.group(1)) if m.group(1) else 0.0
        return f"{whole + _FRACTION_VALUE[m.group(2)]:g}"

    return re.sub(rf"(\d+)?([{_UNICODE_FRACTIONS}])", repl, text)


def _first_qty(text: str) -> tuple[Optional[float], Optional[str]]:
    m = _QTY.search(_fractions_to_decimal(text))
    if not m:
        return None, None
    qty = float(m.group(1))
    if m.group(2):
        denom = float(m.group(2))
        qty = qty / denom if denom else qty
    unit = {"mL": "ml", "cc": "ml", "Ts": "큰술", "T": "큰술", "ts": "작은술", "t": "작은술"}.get(
        m.group(3), m.group(3)
    )
    return round(qty, 3), unit


def _parse_item(raw: str, optional: bool) -> Optional[RecipeIngredient]:
    s = raw.strip(" .·•●-")
    if not s:
        return None
    m = re.match(r"^([^\d(（]+)", s)
    head = m.group(1) if m else ""
    name = clean_name(head)
    if not name:  # 예: '2가지색 파프리카 20g' 처럼 숫자로 시작
        name = clean_name(_QTY.sub(" ", re.sub(r"\([^)]*\)", " ", s)))
    if not name or not re.search(r"[가-힣A-Za-z]", name):
        return None
    qty, unit = _first_qty(s[len(head):])
    return RecipeIngredient(name=name, qty=qty, unit=unit, optional=optional)


def parse_ingredients(text: Optional[str]) -> list[RecipeIngredient]:
    """RCP_PARTS_DTLS 글 → RecipeIngredient 목록."""
    if not text or not text.strip():
        return []
    text = re.sub(r"\[[^\]]*\]", "\n", text)  # [소스소개], [소스] → 줄바꿈
    items: list[RecipeIngredient] = []
    optional = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _is_header_line(line):
            optional = _is_optional_section(line)
            continue
        # 줄 안의 소제목으로 나누기: [앞 글, 소제목1, 글1, 소제목2, 글2, …]
        pieces = _SECTION.split(line)
        segments = [(None, pieces[0])] + [(pieces[i], pieces[i + 1]) for i in range(1, len(pieces) - 1, 2)]
        for label, seg in segments:
            if label is not None:
                optional = _is_optional_section(label)
            # '양파 5g 고추장 9g' 처럼 쉼표 없이 이어진 재료 나누기
            seg = re.sub(rf"(\d(?:{_UNIT_ALT}))\s+(?=[가-힣])", r"\1,", seg)
            for raw in _split_top_level(seg):
                item = _parse_item(raw, optional)
                if item:
                    items.append(item)
    return items


# ── 조리 순서·시간 ─────────────────────────────────────
def clean_steps(row: dict) -> list[str]:
    """MANUAL01~20 → 번호를 뺀 단계 글 목록."""
    steps = []
    for i in range(1, 21):
        v = (row.get(f"MANUAL{i:02d}") or "").strip()
        if not v:
            continue
        v = re.sub(r"\s+", " ", v)
        v = re.sub(r"(?<=[^A-Za-z\s])[a-d]$", "", v)  # 끝에 붙은 a·b·c·d 찌꺼기
        v = re.sub(r"^\d+\s*[.)]\s*", "", v)  # 원래 번호 (가끔 2부터 시작해서 다시 매김)
        if v:
            steps.append(v)
    return steps


def estimate_minutes(way: str, steps: list[str]) -> int:
    """조리 시간 추정(분): 조리법 기본 시간 + 3단계 넘는 단계마다 2분.
    조리 순서에 'N분', 'N시간'이 적혀 있으면 그 합 + 5분과 비교해 큰 값. 5분 단위로 반올림."""
    base = WAY_BASE_MINUTES.get(way.strip(), 15) + max(0, len(steps) - 3) * 2
    text = " ".join(steps)
    mentioned = sum(int(x) for x in re.findall(r"(\d+)\s*분", text))
    mentioned += sum(int(x) * 60 for x in re.findall(r"(\d+)\s*시간", text))
    est = max(base, mentioned + 5) if mentioned else base
    return int(min(180, max(5, 5 * round(est / 5))))


# ── 태그 ───────────────────────────────────────────
def _num(value) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def make_tags(row: dict, ingredients: list[RecipeIngredient]) -> list[str]:
    tags: list[str] = []
    for key in ("RCP_PAT2", "RCP_WAY2"):
        v = (row.get(key) or "").strip()
        if v:
            tags.append(v)
    tags += [t for t in re.split(r"[,#\s]+", row.get("HASH_TAG") or "") if t]
    pro, kcal = _num(row.get("INFO_PRO")), _num(row.get("INFO_ENG"))
    if pro is not None and pro >= HIGH_PROTEIN_G:
        tags.append("고단백")
    if kcal is not None and kcal <= DIET_KCAL:
        tags.append("다이어트")
    if any(w in i.name for i in ingredients for w in SPICY_WORDS):
        tags.append("매운맛")
    return list(dict.fromkeys(tags))  # 순서 유지하며 중복 제거


def _https(url: Optional[str]) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


# ── 한 줄 → Recipe ─────────────────────────────────────
def row_to_recipe(row: dict) -> Optional[Recipe]:
    """API 응답의 row 하나 → Recipe. 제목·재료·조리 순서 중 하나라도 없으면 None."""
    seq = str(row.get("RCP_SEQ") or "").strip()
    title = re.sub(r"\s+", " ", row.get("RCP_NM") or "").strip()
    ingredients = parse_ingredients(row.get("RCP_PARTS_DTLS"))
    steps = clean_steps(row)
    if not seq or not title or not ingredients or not steps:
        return None
    return Recipe(
        id=SOURCE_PREFIX + seq,
        title=title,
        ingredients=ingredients,
        steps="\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1)),
        cook_minutes=estimate_minutes(row.get("RCP_WAY2") or "", steps),
        servings=SERVINGS,
        tags=make_tags(row, ingredients),
        allergens=find_allergens([i.name for i in ingredients] + [title]),
        image_url=_https(row.get("ATT_FILE_NO_MAIN")),
    )


def recipe_to_row(recipe: Recipe) -> dict:
    """Recipe → recipes 표 한 줄 (embedding 제외). source_id 는 recipe.id."""
    return {
        "source_id": recipe.id,
        "title": recipe.title,
        "ingredients": [
            {"name": i.name, "qty": i.qty, "unit": i.unit, "optional": i.optional} for i in recipe.ingredients
        ],
        "steps": recipe.steps,
        "cook_minutes": recipe.cook_minutes,
        "servings": recipe.servings,
        "tags": list(recipe.tags),
        "allergens": list(recipe.allergens),
        "image_url": recipe.image_url,
    }


def embedding_text(recipe: Recipe) -> str:
    """임베딩에 넣을 글: 제목 + 재료 이름 + 태그 (PLAN 5장 ③-2)."""
    names = ", ".join(i.name for i in recipe.ingredients)
    return f"{recipe.title} | 재료: {names} | 태그: {', '.join(recipe.tags)}"
