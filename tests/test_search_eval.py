"""검색 전략 실험의 계산 부분 검사 (lib/search_eval.py) — 네트워크·DB 없이."""
from dataclasses import asdict
from pathlib import Path

import numpy as np

from lib.recipe_import import embedding_text
from lib.search_eval import (
    BM25,
    Config,
    Question,
    build_corpus,
    from_rewrite,
    from_rewrite_strict,
    search,
    hard_filter,
    improved,
    is_correct,
    judge,
    load_questions,
    mmr,
    plain,
    retrieve,
    rrf,
    select,
    summarize,
    tokens,
    QResult,
)
from tests.recipe_fixtures import CUCUMBER_SALAD, DOENJANG_SOUP, SAMPLE_RECIPES, STEAMED_EGG

ROOT = Path(__file__).resolve().parent.parent


def q(**kw) -> Question:
    base = dict(id="T", type="재료형", query="", ingredients=[], must_use=[], tags_all=[], tags_any=[],
                tags_none=[], allergy=[], max_minutes=None)
    return Question(**{**base, **kw})


def corpus():
    """레시피 3개 + 손으로 정한 임베딩 (계란찜·된장국·오이무침 방향)."""
    vecs = [[1, 0, 0], [0, 1, 0], [0.6, 0, 0.8]]
    rows = [({**{k: v for k, v in asdict(r).items() if k != "id"}, "source_id": r.id}, v)
            for r, v in zip(SAMPLE_RECIPES, vecs)]
    return build_corpus(rows, embedding_text)


# ── 질문 파일 ───────────────────────────────────────
def test_question_file_loads_50_questions():
    qs = load_questions(ROOT / "eval" / "search_questions.csv")
    assert len(qs) == 50
    assert sum(x.type == "재료형" for x in qs) == 25
    i21 = next(x for x in qs if x.id == "I21")
    assert i21.ingredients == ["새우", "양파"] and i21.allergy == ["우유"]


# ── 정답 판정 ───────────────────────────────────────
def test_is_correct_conditions():
    assert is_correct(DOENJANG_SOUP, q(must_use=["두부", "대파"]))
    assert not is_correct(DOENJANG_SOUP, q(must_use=["두부", "감자", "새우"]))
    assert is_correct(STEAMED_EGG, q(must_use=["두부"]))  # 연두부
    assert is_correct(DOENJANG_SOUP, q(tags_all=["국&찌개"]))
    assert is_correct(CUCUMBER_SALAD, q(tags_any=["일품", "다이어트"]))
    assert not is_correct(CUCUMBER_SALAD, q(tags_none=["다이어트"]))
    assert not is_correct(CUCUMBER_SALAD, q(allergy=["땅콩"]))
    assert not is_correct(STEAMED_EGG, q(allergy=["계란"]))  # 계란 → 달걀
    assert not is_correct(STEAMED_EGG, q(max_minutes=15))  # 20분


# ── BM25 · RRF · MMR ────────────────────────────────
def test_tokens_are_bigrams_so_tofu_variants_overlap():
    assert tokens("연두부") == ["연두", "두부"]
    assert "두부" in tokens("두부, 대파")


def test_bm25_prefers_documents_with_query_words():
    docs = [tokens("두부 된장국"), tokens("딸기 요거트"), tokens("두부 두부 조림")]
    s = BM25(docs).scores(tokens("두부"))
    assert s[1] == 0 and s[0] > 0 and s[2] > s[0]


def test_rrf_rewards_items_high_in_both_lists():
    assert rrf([[1, 2, 3], [2, 3, 1]])[0] == 2
    assert rrf([[5], []]) == [5]


def test_mmr_skips_near_duplicates():
    v = np.array([[1, 0], [0.99, 0.141], [0, 1]], dtype=float)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    assert mmr([0, 1, 2], v, k=2, lam=1.0) == [0, 1]  # λ=1 이면 순서대로
    assert mmr([0, 1, 2], v, k=2, lam=0.5) == [0, 2]  # 비슷한 1번 대신 2번


# ── 단계 이어 붙이기 ─────────────────────────────────
def test_plain_and_rewrite_prepare_queries():
    p = plain(q(type="재료형", ingredients=["두부", "대파"], max_minutes=15))
    assert (p.text, p.ingredients, p.max_minutes) == ("두부 대파", ["두부", "대파"], 15)
    s = plain(q(type="문장형", query="얼큰한 국", max_minutes=15))
    assert (s.text, s.ingredients, s.max_minutes) == ("얼큰한 국", [], None)  # 문장 속 조건은 못 씀
    r = from_rewrite(q(type="문장형", query="얼큰한 국"), {"ingredients": ["고춧가루"], "tags": ["국&찌개", "없는태그"], "max_minutes": 15})
    assert (r.ingredients, r.tags, r.max_minutes) == (["고춧가루"], ["국&찌개"], 15)


def test_hard_filter_removes_allergy_and_long_recipes():
    c = corpus()
    assert list(hard_filter(c, {"땅콩"}, None)) == [True, True, False]
    assert list(hard_filter(c, set(), 15)) == [False, True, True]


def test_vector_retrieve_threshold_and_rerank():
    c = corpus()
    qvec = np.array([1.0, 0, 0])
    mask = np.ones(3, dtype=bool)
    prep = plain(q(ingredients=["대파"]))
    assert retrieve(c, qvec, prep, Config(), mask) == [0, 2, 1]
    assert retrieve(c, qvec, prep, Config(threshold=0.5), mask) == [0, 2]
    # 코드 점수: 대파를 쓰는 된장국만 남음 (임박 재료를 안 쓰면 뺌)
    assert select(c, [0, 2, 1], prep, Config(rerank=True)) == [1]


def test_bm25_retrieve_only_returns_matching_docs():
    c = corpus()
    prep = plain(q(ingredients=["오이"]))
    assert retrieve(c, np.zeros(3), prep, Config(retrieve="bm25"), np.ones(3, dtype=bool)) == [2]


# ── 채점 · 요약 ─────────────────────────────────────
def test_judge_and_summary():
    c = corpus()
    qq = q(must_use=["두부"], allergy=["땅콩"])
    correct, violations, cats = judge(c, [0, 2], qq)
    assert correct == [True, False] and violations == 1 and cats == 1
    res = [QResult("R", "A", "재료형", [0, 2], correct, violations, cats, 0, 0.1),
           QResult("R", "B", "문장형", [1], [False], 0, 1, 1, 0.3)]
    s = summarize("R", res)
    assert s.hit == {"재료형": 1, "문장형": 0} and s.hits == 1 and s.violations == 1 and s.llm_calls == 1
    assert abs(s.precision - (1 / 3 + 0) / 2) < 1e-9  # 맞은 개수 ÷ 3 의 평균
    assert s.short == 2  # 둘 다 3개보다 적음


def test_precision_counts_missing_slots_as_wrong():
    one = QResult("R", "A", "재료형", [0], [True], 0, 1, 0, 0)  # 1개만 나왔고 맞음
    assert one.short and abs(one.precision - 1 / 3) < 1e-9  # 1.0 이 아니라 1/3


def test_strict_rewrite_skips_ingredient_questions_and_can_keep_tags_out_of_text():
    ing = q(type="재료형", ingredients=["시금치"])
    assert from_rewrite_strict(ing, {"tags": ["다이어트"]}).tags == []  # 재료형은 재작성 안 함
    s = q(type="문장형", query="얼큰한 국")
    data = {"ingredients": ["고춧가루"], "tags": ["국&찌개", "매운맛"]}
    with_tags = from_rewrite_strict(s, data, tags_in_text=True)
    without = from_rewrite_strict(s, data, tags_in_text=False)
    assert "국&찌개" in with_tags.text
    assert without.text == "얼큰한 국 고춧가루" and without.tags == ["국&찌개", "매운맛"]  # 태그는 점수에만


def test_search_expands_candidates_when_too_few(monkeypatch):
    import lib.search_eval as se

    c = corpus()
    seen = []
    real_retrieve = se.retrieve

    def spy(corpus_, qvec, prep, cfg, mask):
        seen.append(cfg.candidates)
        return real_retrieve(corpus_, qvec, prep, cfg, mask)

    monkeypatch.setattr(se, "retrieve", spy)
    prep = plain(q(ingredients=["대파"]))  # 대파를 쓰는 레시피는 1개뿐
    mask = np.ones(3, dtype=bool)
    assert se.search(c, np.array([1.0, 0, 0]), prep, Config(rerank=True, candidates=1, expand=True), mask) == [1]
    assert seen == [1, 100]  # 후보 1개로는 모자라 100개로 늘림 → 레시피가 3개뿐이라 거기서 멈춤
    seen.clear()
    se.search(c, np.array([1.0, 0, 0]), prep, Config(rerank=True, candidates=1), mask)
    assert seen == [1]  # expand 가 꺼져 있으면 늘리지 않음


def test_improved_rule():
    a = summarize("a", [QResult("a", "1", "재료형", [0], [True], 0, 1, 0, 0)])
    b = summarize("b", [QResult("b", "1", "재료형", [0], [False], 0, 1, 0, 0)])
    assert improved(a, b) and not improved(b, a) and not improved(a, a)
