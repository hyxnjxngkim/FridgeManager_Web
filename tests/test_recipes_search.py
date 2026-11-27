"""search_recipes() 검사 — DB·Bedrock 은 가짜로 바꿔 끼워요."""
from dataclasses import asdict

import pytest
from streamlit.testing.v1 import AppTest

import lib.recipes as rec
from lib.models import Recipe, RecipeIngredient, RecipeMatch
from tests.recipe_fixtures import CATALOG, SAMPLE_RECIPES

USER_ID = "user-1"


def _row(r: Recipe) -> dict:
    """DB 가 돌려주는 줄 모양 (ingredients 는 jsonb → dict 목록)."""
    d = asdict(r)
    return {k: d[k] for k in ("id", "title", "ingredients", "steps", "cook_minutes", "servings",
                              "tags", "allergens", "image_url")}


@pytest.fixture
def fake_db(monkeypatch):
    """SQL 을 흉내 내는 가짜 DB. 받은 SQL·값을 calls 에 남겨요."""
    calls = []
    state = {"allergy_values": [], "embed_fails": False}

    def fake_fetch_all(sql, params):
        calls.append((sql, params))
        if "from preferences" in sql:
            assert params == (USER_ID,)
            return [{"value": v} for v in state["allergy_values"]]
        allergies, max_minutes = params[0], params[1]
        rows = [
            _row(r) for r in SAMPLE_RECIPES
            if not set(r.allergens) & set(allergies)
            and (max_minutes is None or (r.cook_minutes or 0) <= max_minutes)
        ]
        return rows[: params[-1]]  # limit

    def fake_embed(text):
        if state["embed_fails"]:
            raise RuntimeError("no bedrock")
        return "[0.1,0.2]"

    monkeypatch.setattr(rec, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(rec, "_embed", fake_embed)
    monkeypatch.setattr(rec, "_user_have", lambda user_id: ["감자", "오이"])
    monkeypatch.setattr(rec, "_catalog", lambda: CATALOG)
    return calls, state


def test_returns_ranked_recipe_matches(fake_db):
    results = rec.search_recipes(USER_ID, ["두부", "대파"])
    assert all(isinstance(m, RecipeMatch) and isinstance(m.recipe, Recipe) for m in results)
    assert all(isinstance(i, RecipeIngredient) for i in results[0].recipe.ingredients)
    assert results[0].recipe.title == "된장국"  # 두부 + 대파
    assert results[0].uses_expiring == ["두부", "대파"]
    assert [m.score for m in results] == sorted((m.score for m in results), reverse=True)


def test_vector_search_sql_has_allergy_filter_and_vector_order(fake_db):
    calls, _ = fake_db
    rec.search_recipes(USER_ID, ["두부"])
    sql, params = calls[-1]
    assert "not (allergens && %s::text[])" in sql
    assert "order by embedding <=> %s::vector" in sql
    assert params[-2:] == ("[0.1,0.2]", rec.CANDIDATES)


def test_user_allergies_are_excluded_and_normalized(fake_db):
    calls, state = fake_db
    state["allergy_values"] = ["땅콩", "계란"]  # A 의 에이전트가 저장한 모양 (kind='allergy')
    titles = [m.recipe.title for m in rec.search_recipes(USER_ID, ["두부"])]
    assert titles == ["된장국"]  # 땅콩·달걀 레시피 빠짐
    assert calls[-1][1][0] == ["달걀", "땅콩"]  # '계란' → '달걀'


def test_max_minutes_is_passed_to_sql(fake_db):
    calls, _ = fake_db
    titles = [m.recipe.title for m in rec.search_recipes(USER_ID, ["두부"], max_minutes=15)]
    assert "새우 두부 계란찜" not in titles  # 20분
    assert calls[-1][1][1:3] == (15, 15)


def test_falls_back_to_text_search_when_embedding_fails(fake_db):
    calls, state = fake_db
    state["embed_fails"] = True
    results = rec.search_recipes(USER_ID, ["두부"])
    sql, params = calls[-1]
    assert "ilike any(%s::text[])" in sql and "<=>" not in sql
    assert params[-2:] == (["%두부%"], rec.CANDIDATES)
    assert results


def test_recipes_without_any_expiring_ingredient_are_dropped(fake_db):
    titles = [m.recipe.title for m in rec.search_recipes(USER_ID, ["대파"])]
    assert titles == ["된장국"]  # 대파를 쓰는 레시피만
    assert rec.search_recipes(USER_ID, ["딸기"]) == []


def _many_recipes_db(monkeypatch, spinach_at: int, total: int = 120):
    """레시피 total 개 중 spinach_at 번째(0부터)만 시금치를 쓰는 가짜 DB. 받은 limit 을 기록해요."""
    rows = [
        _row(Recipe(f"r{i}", f"레시피{i}", [RecipeIngredient("시금치" if i == spinach_at else "오이")], "1. 만든다."))
        for i in range(total)
    ]
    limits = []

    def fake_fetch_all(sql, params):
        if "from preferences" in sql:
            return []
        limits.append(params[-1])
        return rows[: params[-1]]

    monkeypatch.setattr(rec, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(rec, "_embed", lambda text: "[0.1]")
    monkeypatch.setattr(rec, "_user_have", lambda user_id: [])
    monkeypatch.setattr(rec, "_catalog", lambda: [])
    return limits


def test_expands_candidates_when_too_few_results(monkeypatch):
    limits = _many_recipes_db(monkeypatch, spinach_at=110)  # 후보 30·100개 안에는 시금치 레시피가 없음
    results = rec.search_recipes(USER_ID, ["시금치"])
    assert limits == [30, 100, 300]  # 30 → 100 → 300 으로 늘려 다시 찾음
    assert [m.recipe.title for m in results] == ["레시피110"]


def test_stops_expanding_when_db_has_no_more(monkeypatch):
    limits = _many_recipes_db(monkeypatch, spinach_at=50, total=60)
    assert [m.recipe.title for m in rec.search_recipes(USER_ID, ["시금치"])] == ["레시피50"]
    assert limits == [30, 100]  # 100개를 달라 했는데 60개뿐이면 더 늘리지 않음


def test_no_expansion_when_enough_results(fake_db):
    calls, _ = fake_db
    rec.search_recipes(USER_ID, ["두부"])
    assert [p[-1] for s, p in calls if "from recipes" in s] == [30]


def test_tags_only_query_and_empty_query(fake_db):
    assert rec.search_recipes(USER_ID, [], tags=["다이어트"])  # 태그만으로도 검색
    assert rec.search_recipes(USER_ID, []) == []
    assert rec.search_recipes(USER_ID, ["  "]) == []


# ── recipe_card() ─────────────────────────────────────
def _card_script():
    from lib.recipe_rules import score_recipe
    from lib.ui import recipe_card, recipe_data_credit
    from tests.recipe_fixtures import STEAMED_EGG

    recipe_card(score_recipe(STEAMED_EGG, ["두부"], ["연두부"]))
    recipe_data_credit()


def test_recipe_card_shows_info_without_buttons():
    at = AppTest.from_function(_card_script, default_timeout=60)
    at.run()
    assert not at.exception, at.exception

    texts = " ".join(md.value for md in at.markdown) + " " + " ".join(c.value for c in at.caption)
    assert "새우 두부 계란찜" in texts
    assert "구출 재료: `두부`" in texts
    assert "없는 재료: 칵테일새우, 달걀, 생크림, 무염버터" in texts
    assert "연두부 75g" in texts and "시금치 10g(선택)" in texts
    assert "약 20분 (추정)" in texts
    assert "알레르기 성분: 달걀, 우유, 대두, 새우" in texts
    assert "레시피 데이터: 식품안전나라" in texts
    assert at.expander[0].label == "만드는 법"
    assert not at.button  # 버튼은 카드에 넣지 않아요
