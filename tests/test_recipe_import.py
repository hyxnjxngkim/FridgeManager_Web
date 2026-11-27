"""식품안전나라 레시피 → Recipe 변환 검사 (DB·네트워크 없이).

재료 글은 실제 API 응답(COOKRCP01)에 나온 모양을 그대로 옮겼어요.
"""
from lib.allergens import find_allergens, normalize_allergy
from lib.recipe_import import (
    clean_steps,
    embedding_text,
    estimate_minutes,
    parse_ingredients,
    row_to_recipe,
)


def names(text):
    return [i.name for i in parse_ingredients(text)]


def by_name(text):
    return {i.name: i for i in parse_ingredients(text)}


# ── 재료 파싱 ───────────────────────────────────────
def test_title_line_and_garnish_section():
    text = (
        "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개), "
        "생크림 13g(1큰술), 설탕 5g(1작은술), 무염버터 5g(1작은술)\n고명\n시금치 10g(3줄기)"
    )
    items = by_name(text)
    assert list(items) == ["연두부", "칵테일새우", "달걀", "생크림", "설탕", "무염버터", "시금치"]
    assert (items["연두부"].qty, items["연두부"].unit) == (75.0, "g")
    assert items["시금치"].optional is True  # 고명
    assert items["연두부"].optional is False


def test_bullet_sections_with_colon():
    text = "●오이무침 :\n오이 70g(1/3개), 다진 땅콩 10g(1큰술)\n●순두부사과 소스 : \n순두부 40g(1/8봉지), 사과 50g(1/3개)"
    assert names(text) == ["오이", "다진 땅콩", "순두부", "사과"]


def test_parentheses_style_and_commas_inside_parentheses():
    text = "닭고기(가슴살, 30g), 쌀(50g), 양파(10g),\n대추(2알), 파프리카(1/4개)"
    items = by_name(text)
    assert list(items) == ["닭고기", "쌀", "양파", "대추", "파프리카"]
    assert (items["닭고기"].qty, items["닭고기"].unit) == (30.0, "g")
    assert (items["파프리카"].qty, items["파프리카"].unit) == (0.25, "개")


def test_inline_section_labels_and_brackets():
    text = (
        "도라지 25g, 검은깨 1.25g, 튀김가루 10g, 식용유 3g[소스소개] "
        "저나트륨 간장소스:간장 1g, 식초 2g"
    )
    assert names(text) == ["도라지", "검은깨", "튀김가루", "식용유", "간장", "식초"]


def test_labels_without_comma_before_them():
    text = "주재료: 시금치(포항초) 30, 적양파 10, 비트 10 드레싱: 발사믹식초 5, 소금 0.38"
    items = by_name(text)
    assert list(items) == ["시금치", "적양파", "비트", "발사믹식초", "소금"]
    assert items["시금치"].qty == 30.0 and items["시금치"].unit is None  # 단위 없는 숫자


def test_glued_header_words_are_removed():
    text = "재료 콩고기(30g), 아보카도(10g)\n저염간장양념 저염간장(2.5g), 물(25g)\n양념 들깻가루(15g)"
    assert names(text) == ["콩고기", "아보카도", "저염간장", "물", "들깻가루"]


def test_vague_amounts_ranges_fractions_and_spoons():
    text = "소금적당량, 후춧가루(약간), 토마토(2~3개), 양파(½개), 물 300ml(1½컵), 올리브유(1Ts)"
    items = by_name(text)
    assert list(items) == ["소금", "후춧가루", "토마토", "양파", "물", "올리브유"]
    assert items["소금"].qty is None and items["후춧가루"].qty is None
    assert (items["토마토"].qty, items["토마토"].unit) == (2.0, "개")  # 범위는 앞 숫자
    assert (items["양파"].qty, items["양파"].unit) == (0.5, "개")
    assert (items["물"].qty, items["물"].unit) == (300.0, "ml")
    assert (items["올리브유"].qty, items["올리브유"].unit) == (1.0, "큰술")


def test_items_without_commas_between_them():
    assert names("오이 10g, 양파 5g 고추장 9g, 식초 6g") == ["오이", "양파", "고추장", "식초"]


def test_empty_text():
    assert parse_ingredients("") == []
    assert parse_ingredients(None) == []


# ── 조리 순서·시간 ───────────────────────────────────
def test_steps_are_cleaned_and_renumbered():
    row = {
        "MANUAL01": "2. 손질된 새우를 끓는 물에 데쳐 건진다.a",
        "MANUAL02": "3. 찜기에 넣고\n중간 불에서 10분 정도 찐다.c",
        "MANUAL03": "",
    }
    assert clean_steps(row) == ["손질된 새우를 끓는 물에 데쳐 건진다.", "찜기에 넣고 중간 불에서 10분 정도 찐다."]


def test_estimate_minutes():
    assert estimate_minutes("기타", ["a", "b", "c"]) == 10  # 기본 10분
    assert estimate_minutes("끓이기", ["a"] * 6) == 30  # 25 + 3단계 × 2 = 31 → 30
    assert estimate_minutes("기타", ["30분 정도 재운다", "b", "c"]) == 35  # 적힌 30분 + 5
    assert estimate_minutes("굽기", ["1시간 굽는다"]) == 65
    assert estimate_minutes("모름", ["a"]) == 15  # 모르는 조리법은 15분


# ── 한 줄 전체 ──────────────────────────────────────
ROW_28 = {
    "RCP_SEQ": "28",
    "RCP_NM": "새우 두부 계란찜",
    "RCP_WAY2": "찌기",
    "RCP_PAT2": "반찬",
    "HASH_TAG": "연두부",
    "INFO_ENG": "220",
    "INFO_PRO": "14",
    "ATT_FILE_NO_MAIN": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png",
    "RCP_PARTS_DTLS": (
        "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개), "
        "생크림 13g(1큰술), 설탕 5g(1작은술), 무염버터 5g(1작은술)\n고명\n시금치 10g(3줄기)"
    ),
    "MANUAL01": "1. 손질된 새우를 끓는 물에 데쳐 건진다.a",
    "MANUAL02": "2. 연두부, 달걀, 생크림, 설탕에 녹인 무염버터를 믹서에 넣고 간 뒤 새우(1)를 함께 섞어 그릇에 담는다.b",
    "MANUAL03": "3. 시금치를 잘게 다져 혼합물 그릇(2)에 뿌리고 찜기에 넣고 중간 불에서 10분 정도 찐다.c",
}


def test_row_to_recipe():
    r = row_to_recipe(ROW_28)
    assert r is not None
    assert r.id == "foodsafety:28"  # DB 의 source_id
    assert r.title == "새우 두부 계란찜"
    assert r.servings == 1
    assert r.cook_minutes == 20  # 찌기 20분, 적힌 10분 + 5 보다 큼
    assert r.steps.splitlines()[0] == "1. 손질된 새우를 끓는 물에 데쳐 건진다."
    assert r.tags == ["반찬", "찌기", "연두부"]  # 단백질 14g(<15), 220kcal(>150)
    assert r.allergens == ["달걀", "우유", "대두", "새우"]
    assert r.image_url == "https://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png"
    assert r.source_name is None and r.source_url is None  # 레시피별 출처는 넣지 않음


def test_protein_diet_and_spicy_tags():
    row = dict(ROW_28, INFO_PRO="20", INFO_ENG="120", HASH_TAG="",
               RCP_PARTS_DTLS="두부 100g, 고춧가루 2g")
    assert row_to_recipe(row).tags == ["반찬", "찌기", "고단백", "다이어트", "매운맛"]


def test_kimchi_and_dried_chili_are_spicy_but_white_kimchi_is_not():
    def tags(parts):
        return row_to_recipe(dict(ROW_28, HASH_TAG="", RCP_PARTS_DTLS=parts)).tags

    assert "매운맛" in tags("두부 100g, 김치 50g")
    assert "매운맛" in tags("돼지고기 100g, 배추김치 80g")
    assert "매운맛" in tags("멸치 10g, 건고추 2개")
    assert "매운맛" not in tags("닭가슴살 100g, 백김치 50g")
    assert "매운맛" not in tags("국수 100g, 물김치국물 200ml")
    assert "매운맛" not in tags("장어 100g, 명이김치 20g")
    assert "매운맛" not in tags("두부 100g, 홍고추 5g")  # 장식용 고추는 넣지 않음


def test_rows_missing_parts_or_steps_are_skipped():
    assert row_to_recipe(dict(ROW_28, RCP_PARTS_DTLS="")) is None
    no_steps = {k: v for k, v in ROW_28.items() if not k.startswith("MANUAL")}
    assert row_to_recipe(no_steps) is None


def test_embedding_text():
    text = embedding_text(row_to_recipe(ROW_28))
    assert text.startswith("새우 두부 계란찜 | 재료: 연두부, 칵테일새우")
    assert "태그: 반찬, 찌기, 연두부" in text


# ── 알레르기 사전 ────────────────────────────────────
def test_find_allergens():
    assert find_allergens(["오이", "다진 땅콩", "순두부", "사과"]) == ["땅콩", "대두"]
    assert find_allergens(["땅콩"]) == ["땅콩"]  # '땅콩'의 '콩'은 대두로 보지 않음
    assert find_allergens(["저염간장"]) == ["대두", "밀"]
    assert find_allergens(["메추리알", "모차렐라치즈", "치킨육수"]) == ["달걀", "우유", "닭고기"]
    assert find_allergens(["오이", "양파"]) == []


def test_normalize_allergy_words_from_users():
    assert normalize_allergy("계란") == ["달걀"]
    assert normalize_allergy("갑각류") == ["새우", "게"]
    assert normalize_allergy(" 땅콩 ") == ["땅콩"]
    assert normalize_allergy("소고기") == ["쇠고기"]
    assert normalize_allergy("키위") == ["키위"]  # 사전에 없으면 그대로
    assert normalize_allergy("") == []
