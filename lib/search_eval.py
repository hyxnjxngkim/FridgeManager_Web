"""검색 전략 실험 — 계산 부분만 (순수 함수, DB·네트워크 없음). 실행은 scripts/eval_search.py.

검색을 세 단계로 나누고, 단계마다 전략을 골라 이어 붙여요.
    ① 질문 다듬기: plain(그대로) / rewrite(질문 재작성) / hyde(가짜 레시피)
                   / rewrite_strict(엄격한 재작성: 근거 없는 태그 금지, 재료형은 재작성 안 함)
                   / rewrite_strict_q(엄격한 재작성 + 태그는 점수에만, 검색어 글은 원래 문장 + 재료)
    ② 찾기:        vector / bm25(키워드) / rrf(벡터 + 키워드 순위 합치기)
    ③ 고르기:      Top-k / + 코드 점수(score_recipe) / + 거리 임계값 / + MMR
                   / + 후보 늘리기(결과가 k개보다 적으면 후보 30 → 100 → 300)

모든 전략에서 알레르기·조리 시간은 먼저 걸러요 (앱의 SQL 하드 필터와 같음).
"""
from __future__ import annotations

import csv
import math
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from lib.allergens import normalize_allergy
from lib.models import Recipe, RecipeIngredient
from lib.recipe_rules import _same_key, rank, score_recipe

CATEGORIES = ("반찬", "국&찌개", "일품", "밥", "후식", "기타")
# 질문 재작성·HyDE 가 쓸 수 있는 태그 (레시피 데이터에 실제로 있는 태그)
TAG_VOCAB = ("반찬", "국&찌개", "일품", "밥", "후식", "끓이기", "굽기", "볶기", "찌기", "튀기기",
             "고단백", "다이어트", "매운맛")
# 실험용 냉장고 (보유 비율 계산에만 씀) — 흔한 재료 + 양념
FRIDGE = ["양파", "대파", "마늘", "달걀", "우유", "두부", "감자", "당근", "김치", "고추장", "된장", "간장"]
RRF_K = 60


# ── 질문 ────────────────────────────────────────────
@dataclass
class Question:
    id: str
    type: str  # 재료형 / 문장형
    query: str
    ingredients: list[str]
    must_use: list[str]
    tags_all: list[str]
    tags_any: list[str]
    tags_none: list[str]
    allergy: list[str]
    max_minutes: Optional[int]
    group: str = ""


def _split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split("|") if x.strip()]


def load_questions(path: Path) -> list[Question]:
    with open(path, encoding="utf-8") as f:
        return [
            Question(
                id=r["id"], type=r["type"], query=r["query"], ingredients=_split(r["ingredients"]),
                must_use=_split(r["must_use"]), tags_all=_split(r["tags_all"]), tags_any=_split(r["tags_any"]),
                tags_none=_split(r["tags_none"]), allergy=_split(r["allergy"]),
                max_minutes=int(r["max_minutes"]) if r["max_minutes"].strip() else None, group=r.get("group", ""),
            )
            for r in csv.DictReader(f)
        ]


def allergy_names(q: Question) -> set[str]:
    return {a for w in q.allergy for a in normalize_allergy(w)}


def is_correct(recipe: Recipe, q: Question) -> bool:
    """정답 조건: 꼭 쓸 재료를 모두 쓰고, 태그 조건을 만족하고, 알레르기·시간 조건을 지킴."""
    names = [i.name.replace(" ", "") for i in recipe.ingredients if not i.optional]
    if not all(any(_same_key(u.replace(" ", ""), n) for n in names) for u in q.must_use):
        return False
    tags = set(recipe.tags)
    if not set(q.tags_all) <= tags:
        return False
    if q.tags_any and not tags & set(q.tags_any):
        return False
    if tags & set(q.tags_none):
        return False
    if set(recipe.allergens) & allergy_names(q):
        return False
    if q.max_minutes is not None and (recipe.cook_minutes or 10**6) > q.max_minutes:
        return False
    return True


# ── 레시피 모음 (시드 파일 한 줄 = 레시피 하나) ─────────────────
def tokens(text: str) -> list[str]:
    """BM25 낱말: 띄어쓰기로 나눈 뒤 두 글자씩 (한국어라 '연두부'·'두부'가 '두부'로 겹치게)."""
    out: list[str] = []
    for w in re.findall(r"[0-9A-Za-z가-힣&]+", (text or "").lower()):
        out += [w] if len(w) < 2 else [w[i:i + 2] for i in range(len(w) - 1)]
    return out


class BM25:
    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=float)
        self.avg = float(self.len.mean()) if len(docs) else 0.0
        n = len(docs)
        df = Counter(t for d in self.tf for t in d)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: Sequence[str]) -> np.ndarray:
        s = np.zeros(len(self.tf))
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            f = np.array([d.get(t, 0) for d in self.tf], dtype=float)
            s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len / (self.avg or 1)))
        return s


@dataclass
class Corpus:
    recipes: list[Recipe]
    vectors: np.ndarray  # (레시피 수, 1024), 크기 1로 정규화
    texts: list[str]
    bm25: BM25

    def category(self, i: int) -> str:
        return next((t for t in self.recipes[i].tags if t in CATEGORIES), "기타")


def build_corpus(rows: Sequence[tuple[dict, Sequence[float]]], text_of) -> Corpus:
    """rows: (시드 한 줄, 임베딩). text_of: Recipe → 검색용 글 (lib.recipe_import.embedding_text)."""
    recipes = [
        Recipe(
            id=r["source_id"], title=r["title"],
            ingredients=[RecipeIngredient(**i) for i in r["ingredients"]],
            steps=r["steps"], cook_minutes=r["cook_minutes"], servings=r["servings"],
            tags=list(r["tags"]), allergens=list(r["allergens"]), image_url=r.get("image_url"),
        )
        for r, _ in rows
    ]
    vecs = np.array([v for _, v in rows], dtype=float)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    texts = [text_of(r) for r in recipes]
    return Corpus(recipes, vecs, texts, BM25([tokens(t) for t in texts]))


# ── ① 질문 다듬기 결과 ──────────────────────────────────
@dataclass
class Prepared:
    text: str  # 임베딩·BM25 에 넣을 글
    ingredients: list[str]  # 코드 점수의 '임박 재료'
    tags: list[str]  # 코드 점수의 '원하는 태그'
    max_minutes: Optional[int]


def plain(q: Question) -> Prepared:
    """그대로: 재료형은 재료 이름, 문장형은 문장. 바쁜 날 같은 구조화된 조건은 재료형만 (앱의 일정에서 옴)."""
    if q.type == "재료형":
        return Prepared(" ".join(q.ingredients), list(q.ingredients), [], q.max_minutes)
    return Prepared(q.query, [], [], None)


def from_rewrite(q: Question, data: dict) -> Prepared:
    """재작성: Claude 가 돌려준 {ingredients, tags, max_minutes} (목록에 없는 태그는 버림)."""
    ings = [str(x).strip() for x in (data.get("ingredients") or []) if str(x).strip()]
    tags = [t for t in (data.get("tags") or []) if t in TAG_VOCAB]
    mm = data.get("max_minutes")
    mm = int(mm) if isinstance(mm, (int, float)) and mm > 0 else None
    if q.type == "재료형":  # 재료형의 재료·바쁜 날은 원래 정해진 값
        ings, mm = list(q.ingredients), q.max_minutes
    text = " ".join([*ings, *tags]) or q.query
    return Prepared(text, ings, tags, mm)


def from_rewrite_strict(q: Question, data: dict, tags_in_text: bool = True) -> Prepared:
    """엄격한 재작성. 재료형은 다듬을 게 없어서 그대로(plain) 써요 (Claude 를 부르지 않음).

    tags_in_text=False 면 태그는 점수에만 쓰고, 검색어 글은 '원래 문장 + 재료'로 해요.
    (잘못 붙은 태그 하나가 벡터 후보 30개를 통째로 바꾸는 것을 막으려고)
    """
    if q.type == "재료형":
        return plain(q)
    p = from_rewrite(q, data)
    if not tags_in_text:
        p.text = " ".join([q.query, *p.ingredients])
    return p


def from_hyde(q: Question, fake_recipe: str) -> Prepared:
    """HyDE: 가짜 레시피 글로 찾기. 재료·태그를 따로 뽑지는 않아요 (그건 재작성의 일)."""
    base = plain(q)
    return Prepared(fake_recipe.strip() or base.text, base.ingredients, [], base.max_minutes)


# ── 실험 설정 ───────────────────────────────────────────
@dataclass(frozen=True)
class Config:
    query: str = "plain"  # plain / rewrite / hyde
    retrieve: str = "vector"  # vector / bm25 / rrf
    rerank: bool = False  # 코드 점수
    threshold: Optional[float] = None  # 벡터 유사도가 이보다 낮으면 버림
    mmr: Optional[float] = None  # MMR λ (관련도 비중)
    expand: bool = False  # 결과가 k개보다 적으면 후보 늘려 다시 찾기
    k: int = 3
    candidates: int = 30

    def name(self) -> str:
        parts = [{"plain": "그대로", "rewrite": "재작성", "hyde": "HyDE", "rewrite_strict": "재작성(엄격)",
                  "rewrite_strict_q": "재작성(엄격, 태그는 점수만)"}[self.query],
                 {"vector": "벡터", "bm25": "BM25", "rrf": "벡터+BM25(RRF)"}[self.retrieve]]
        if self.rerank:
            parts.append("코드 점수")
        if self.threshold is not None:
            parts.append(f"임계값 {self.threshold:g}")
        if self.mmr is not None:
            parts.append(f"MMR λ={self.mmr:g}")
        if self.expand:
            parts.append("후보 늘리기")
        return " + ".join(parts) + f" + Top-{self.k}"

    def with_(self, **kw) -> "Config":
        return replace(self, **kw)


# ── ② 찾기 ─────────────────────────────────────────────
def hard_filter(corpus: Corpus, allergies: set[str], max_minutes: Optional[int]) -> np.ndarray:
    ok = np.ones(len(corpus.recipes), dtype=bool)
    for i, r in enumerate(corpus.recipes):
        if allergies & set(r.allergens):
            ok[i] = False
        elif max_minutes is not None and (r.cook_minutes or 10**6) > max_minutes:
            ok[i] = False
    return ok


def _order(scores: np.ndarray, mask: np.ndarray, limit: int, positive_only: bool = False) -> list[int]:
    idx = np.where(mask & (scores > 0) if positive_only else mask)[0]
    return [int(i) for i in idx[np.argsort(-scores[idx], kind="stable")][:limit]]


def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    """여러 순위 목록 → 1/(k+순위) 합으로 다시 줄 세우기 (순위는 1부터)."""
    total: dict[int, float] = {}
    for ranking in rankings:
        for pos, i in enumerate(ranking, start=1):
            total[i] = total.get(i, 0.0) + 1.0 / (k + pos)
    return sorted(total, key=lambda i: (-total[i], i))


def retrieve(corpus: Corpus, qvec: np.ndarray, prep: Prepared, cfg: Config, mask: np.ndarray) -> list[int]:
    sims = corpus.vectors @ qvec
    if cfg.retrieve == "vector":
        order = _order(sims, mask, cfg.candidates)
    elif cfg.retrieve == "bm25":
        order = _order(corpus.bm25.scores(tokens(prep.text)), mask, cfg.candidates, positive_only=True)
    elif cfg.retrieve == "rrf":
        deep = cfg.candidates * 3
        order = rrf([_order(sims, mask, deep),
                     _order(corpus.bm25.scores(tokens(prep.text)), mask, deep, positive_only=True)])[:cfg.candidates]
    else:
        raise ValueError(cfg.retrieve)
    if cfg.threshold is not None:
        order = [i for i in order if sims[i] >= cfg.threshold]
    return order


# ── ③ 고르기 ───────────────────────────────────────────
def mmr(order: Sequence[int], vectors: np.ndarray, k: int, lam: float) -> list[int]:
    """앞 순서일수록 관련도 높음으로 보고, 이미 고른 것과 비슷하면 깎아요."""
    if not order:
        return []
    n = len(order)
    rel = {i: 1.0 - pos / n for pos, i in enumerate(order)}
    chosen: list[int] = []
    rest = list(order)
    while rest and len(chosen) < k:
        def value(i: int) -> float:
            sim = max((float(vectors[i] @ vectors[j]) for j in chosen), default=0.0)
            return lam * rel[i] - (1 - lam) * sim
        best = max(rest, key=value)
        chosen.append(best)
        rest.remove(best)
    return chosen


def select(corpus: Corpus, order: list[int], prep: Prepared, cfg: Config, fridge: Sequence[str] = FRIDGE) -> list[int]:
    if cfg.rerank and order:
        have = [*fridge, *prep.ingredients]
        by_id = {corpus.recipes[i].id: i for i in order}
        matches = [score_recipe(corpus.recipes[i], prep.ingredients, have, prep.tags) for i in order]
        if prep.ingredients:  # 앱과 같이: 임박 재료를 하나도 안 쓰면 뺌
            matches = [m for m in matches if m.uses_expiring]
        order = [by_id[m.recipe.id] for m in rank(matches)]
    if cfg.mmr is not None:
        return mmr(order, corpus.vectors, cfg.k, cfg.mmr)
    return order[:cfg.k]


EXPAND_STEPS = (100, 300)  # 앱(lib/recipes.CANDIDATE_STEPS)과 같은 단계


def search(corpus: Corpus, qvec: np.ndarray, prep: Prepared, cfg: Config, mask: np.ndarray) -> list[int]:
    """② 찾기 + ③ 고르기. cfg.expand 면 결과가 k개보다 적을 때 후보를 늘려 다시 찾아요."""
    steps = (cfg.candidates, *EXPAND_STEPS) if cfg.expand else (cfg.candidates,)
    top: list[int] = []
    for n in steps:
        c = cfg.with_(candidates=n)
        order = retrieve(corpus, qvec, prep, c, mask)
        top = select(corpus, order, prep, c)
        if len(top) >= cfg.k or len(order) < n:  # 충분하거나, 더 가져올 후보가 없으면 멈춤
            break
    return top


# ── 채점 ────────────────────────────────────────────────
@dataclass
class QResult:
    run: str
    qid: str
    qtype: str
    top: list[int]
    correct: list[bool]
    allergy_violations: int
    categories: int
    llm_calls: int
    seconds: float
    note: str = ""
    k: int = 3

    @property
    def hit(self) -> int:
        return int(any(self.correct))

    @property
    def precision(self) -> float:
        """맞은 개수 ÷ k. 결과가 k개보다 적으면 빈자리는 틀린 것으로 세요 (적게 보여 줄수록 점수가 오르지 않게)."""
        return sum(self.correct) / self.k

    @property
    def short(self) -> bool:
        return len(self.top) < self.k


def judge(corpus: Corpus, top: list[int], q: Question) -> tuple[list[bool], int, int]:
    correct = [is_correct(corpus.recipes[i], q) for i in top]
    allergies = allergy_names(q)
    violations = sum(bool(allergies & set(corpus.recipes[i].allergens)) for i in top)
    cats = len({corpus.category(i) for i in top})
    return correct, violations, cats


@dataclass
class Summary:
    run: str
    hit: dict = field(default_factory=dict)  # 종류 → Hit 수
    total: dict = field(default_factory=dict)  # 종류 → 질문 수
    precision: float = 0.0  # Precision@k 평균 (전체)
    short: int = 0  # 결과가 k개보다 적었던 질문 수
    violations: int = 0
    categories: float = 0.0
    llm_calls: int = 0
    seconds: float = 0.0

    @property
    def hits(self) -> int:
        return sum(self.hit.values())

    def key(self) -> tuple:
        """더 좋은 쪽이 큰 값: Hit 합 → Precision → (같으면) Claude 호출이 적은 쪽."""
        return (self.hits, round(self.precision, 6), -self.llm_calls)


def summarize(run: str, results: Sequence[QResult]) -> Summary:
    s = Summary(run)
    for r in results:
        s.hit[r.qtype] = s.hit.get(r.qtype, 0) + r.hit
        s.total[r.qtype] = s.total.get(r.qtype, 0) + 1
    n = max(1, len(results))
    s.precision = sum(r.precision for r in results) / n
    s.short = sum(r.short for r in results)
    s.violations = sum(r.allergy_violations for r in results)
    s.categories = sum(r.categories for r in results) / n
    s.llm_calls = sum(r.llm_calls for r in results)
    s.seconds = sum(r.seconds for r in results) / n
    return s


def improved(new: Summary, old: Summary) -> bool:
    """슬라이드의 '고르는 법': Hit 합이 오르거나, 같으면 Precision 이 오를 때만 남김."""
    return (new.hits, round(new.precision, 6)) > (old.hits, round(old.precision, 6))
