"""검색 전략 실험 실행 — DB 없이 시드 파일(레시피 + 임베딩)과 질문 50개로 채점해요.

사용법 (프로젝트 루트에서, Bedrock 을 쓰니 로컬은 aws login 먼저)
    python scripts/eval_search.py --all                  # R0 → R6 순서대로 (한 번에 한 단계씩 바꿔 보기)
    python scripts/eval_search.py --all --no-llm         # Claude 없이 (재작성·HyDE 단계 건너뜀)
    python scripts/eval_search.py --config "rewrite,rrf,rerank,mmr=0.7"   # 조합 하나만
    python scripts/eval_search.py --all --only I01,Q01   # 질문 몇 개만 (빠른 확인)

--config 낱말: plain|rewrite|hyde|rewrite_strict|rewrite_strict_q, vector|bm25|rrf, rerank, expand,
              threshold=0.15, mmr=0.7, k=3

결과 (eval/results/)
    summary.md       실행별 점수표 + 남긴 단계 + 질문별로 좋아지고/나빠진 것
    details.csv      실행·질문별 상위 k개 레시피와 정답 여부
    llm_cache.json   재작성·HyDE 에 Claude 가 돌려준 글 (다시 돌려도 같은 결과가 나오게)
    cache/           질문 임베딩 저장 (git 에 올리지 않음)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from lib.search_eval import (  # noqa: E402
    TAG_VOCAB,
    Config,
    Corpus,
    Question,
    QResult,
    Summary,
    allergy_names,
    build_corpus,
    from_hyde,
    from_rewrite,
    from_rewrite_strict,
    hard_filter,
    improved,
    judge,
    load_questions,
    plain,
    search,
    summarize,
)

QUESTIONS = ROOT / "eval" / "search_questions.csv"
SEED = ROOT / "db" / "seed" / "recipes_seed.jsonl.gz"
OUT = ROOT / "eval" / "results"
# 유사도 크기는 질문마다 달라요 (예: '닭가슴살' 1위 0.45, '대파, 두부' 1위 0.23·정답 0.13~0.18).
# 그래서 낮은 값부터 비교해요.
THRESHOLDS = (0.1, 0.15, 0.2)
MMR_LAMBDAS = (0.5, 0.7)

REWRITE_PROMPT = """다음 요리 요청을 레시피 검색 조건으로 바꿔 JSON 하나로만 답하세요. 설명은 쓰지 마세요.
{{"ingredients": [요청에 나온 재료 이름], "tags": [아래 태그 중 맞는 것], "max_minutes": 최대 조리 시간(분, 없으면 null)}}
태그 목록: {tags}
요청: {query}"""

# 엄격한 재작성: 근거 없는 태그·재료를 지어내지 않게 규칙과 예시를 줘요.
# 예시는 실험 질문 50개에 없는 것만 써요 (정답을 알려 주지 않게).
STRICT_REWRITE_PROMPT = """다음 요리 요청을 레시피 검색 조건으로 바꿔 JSON 하나로만 답하세요. 설명은 쓰지 마세요.
{"ingredients": [재료 이름], "tags": [태그], "max_minutes": 숫자 또는 null}

규칙
- ingredients: 요청에 직접 나온 재료만 넣으세요. 재료를 지어내지 마세요.
- tags: 그 뜻이 요청에 직접 드러날 때만 아래 목록에서 고르세요. 근거가 없으면 빈 목록 []으로 두세요.
- '맵지 않은', '~ 말고', '~ 싫어'처럼 빼 달라는 조건은 tags 에 넣지 마세요.
- max_minutes: 시간이 숫자로 나오면 그 숫자, 아니면 null.
태그 목록: {tags}

예시
요청: 양배추 → {"ingredients": ["양배추"], "tags": [], "max_minutes": null}
요청: 칼칼한 찌개 끓여 줘 → {"ingredients": [], "tags": ["국&찌개", "매운맛"], "max_minutes": null}
요청: 연어로 뭐 해 먹지? 느끼한 건 싫어 → {"ingredients": ["연어"], "tags": [], "max_minutes": null}
요청: 바빠서 10분 안에 되는 반찬 → {"ingredients": [], "tags": ["반찬"], "max_minutes": 10}

요청: {query}"""

HYDE_PROMPT = """다음 요청에 딱 맞는 한국 가정 요리 레시피 하나를 상상해서, 아래 모양 한 줄로만 쓰세요. 설명은 쓰지 마세요.
요리 이름 | 재료: 재료1, 재료2, ... | 태그: 태그1, 태그2
태그는 이 목록에서만: {tags}
요청: {query}"""


# ── 바깥 호출 (Titan·Claude) — 결과를 파일에 저장해 두고 다시 쓰기 ──────────
class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, key: str):
        return self.data.get(key)

    def put(self, key: str, value) -> None:
        self.data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


class Outside:
    def __init__(self, out: Path, use_llm: bool):
        self.emb = Cache(out / "cache" / "query_embeddings.json")
        self.llm = Cache(out / "llm_cache.json")
        self.use_llm = use_llm
        self._client = None

    def embed(self, text: str) -> tuple[np.ndarray, float]:
        hit = self.emb.get(text)
        if hit is None:
            from lib.embeddings import embed_text

            t = time.perf_counter()
            vec = embed_text(text)
            hit = {"vec": vec, "seconds": time.perf_counter() - t}
            self.emb.put(text, hit)
        v = np.array(hit["vec"], dtype=float)
        return v / np.linalg.norm(v), hit["seconds"]

    def claude(self, kind: str, prompt: str) -> tuple[str, float]:
        key = f"{kind}|{prompt}"
        hit = self.llm.get(key)
        if hit is None:
            if not self.use_llm:
                raise RuntimeError("--no-llm 인데 Claude 가 필요해요")
            from lib.config import CLAUDE_MODEL
            from lib.llm import get_client

            t = time.perf_counter()
            # anthropic 1.x SDK 는 temperature 를 받지 않아요. 대신 돌려준 글을 llm_cache.json 에 저장해
            # 다시 돌려도 같은 결과가 나오게 해요.
            msg = get_client().messages.create(
                model=CLAUDE_MODEL, max_tokens=300, messages=[{"role": "user", "content": prompt}]
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            hit = {"text": text, "seconds": time.perf_counter() - t}
            self.llm.put(key, hit)
        return hit["text"], hit["seconds"]


def _json_object(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def prepare(q: Question, cfg: Config, outside: Outside):
    """① 질문 다듬기 → (Prepared, Claude 호출 수, 걸린 초, 메모)"""
    tags = ", ".join(TAG_VOCAB)
    if cfg.query == "plain":
        return plain(q), 0, 0.0, ""
    if cfg.query == "rewrite":
        text, sec = outside.claude("rewrite", REWRITE_PROMPT.format(tags=tags, query=q.query))
        return from_rewrite(q, _json_object(text)), 1, sec, text.replace("\n", " ")
    if cfg.query in ("rewrite_strict", "rewrite_strict_q"):
        tags_in_text = cfg.query == "rewrite_strict"
        if q.type == "재료형":  # 재료 목록은 다듬을 게 없어서 Claude 를 부르지 않아요
            return from_rewrite_strict(q, {}, tags_in_text), 0, 0.0, "(재료형: 재작성 안 함)"
        prompt = STRICT_REWRITE_PROMPT.replace("{tags}", tags).replace("{query}", q.query)
        text, sec = outside.claude("rewrite_strict", prompt)
        return from_rewrite_strict(q, _json_object(text), tags_in_text), 1, sec, text.replace("\n", " ")
    if cfg.query == "hyde":
        text, sec = outside.claude("hyde", HYDE_PROMPT.format(tags=tags, query=q.query))
        line = next((ln for ln in text.splitlines() if "|" in ln), text)
        return from_hyde(q, line), 1, sec, line
    raise ValueError(cfg.query)


# ── 실행 ────────────────────────────────────────────────
def load_corpus(path: Path) -> Corpus:
    from lib.recipe_import import embedding_text

    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.append((r, r.pop("embedding")))
    return build_corpus(rows, embedding_text)


def run_config(name: str, cfg: Config, corpus: Corpus, questions: list[Question], outside: Outside) -> list[QResult]:
    results = []
    for q in questions:
        prep, calls, llm_sec, note = prepare(q, cfg, outside)
        qvec, emb_sec = outside.embed(prep.text)
        t0 = time.perf_counter()
        mask = hard_filter(corpus, allergy_names(q), prep.max_minutes)
        top = search(corpus, qvec, prep, cfg, mask)
        local = time.perf_counter() - t0
        correct, violations, cats = judge(corpus, top, q)
        # 질문당 시간 = 검색 계산 + (Claude·Titan 을 처음 불렀을 때 걸린 시간, 저장해 둔 값)
        # 처음 부를 때도 저장해 둔 값만 더해서, 두 번 세지 않아요
        seconds = local + llm_sec + emb_sec
        results.append(QResult(name, q.id, q.type, top, correct, violations, cats, calls, seconds, note, k=cfg.k))
    return results


def parse_config(spec: str) -> Config:
    cfg = Config()
    for word in [w.strip() for w in spec.split(",") if w.strip()]:
        if word in ("plain", "rewrite", "hyde", "rewrite_strict", "rewrite_strict_q"):
            cfg = cfg.with_(query=word)
        elif word in ("vector", "bm25", "rrf"):
            cfg = cfg.with_(retrieve=word)
        elif word == "rerank":
            cfg = cfg.with_(rerank=True)
        elif word == "expand":
            cfg = cfg.with_(expand=True)
        elif word.startswith("threshold="):
            cfg = cfg.with_(threshold=float(word.split("=")[1]))
        elif word.startswith("mmr="):
            cfg = cfg.with_(mmr=float(word.split("=")[1]))
        elif word.startswith("k="):
            cfg = cfg.with_(k=int(word.split("=")[1]))
        else:
            sys.exit(f"모르는 설정: {word}")
    return cfg


def ablation(corpus, questions, outside, use_llm: bool):
    """기준에서 한 번에 한 단계씩 바꾸고, 좋아질 때만 남겨요. → [(실행 이름, 설정, 결과, 요약, 남김?)]"""
    log = []

    def try_(label: str, cfg: Config, keep_if=None):
        res = run_config(f"{label}: {cfg.name()}", cfg, corpus, questions, outside)
        s = summarize(res[0].run if res else label, res)
        print(f"  {s.run}  → Hit {s.hits}/{len(questions)}  P@{cfg.k} {s.precision:.2f}")
        return res, s

    base = Config()
    res, best_s = try_("R0 기준", base)
    best = base
    log.append(("R0", base, res, best_s, True))

    res, s = try_("R-참고 BM25만", base.with_(retrieve="bm25"))
    log.append(("R-참고", base.with_(retrieve="bm25"), res, s, None))

    def step(tag: str, label: str, cfg: Config):
        nonlocal best, best_s
        res, s = try_(f"{tag} {label}", cfg)
        keep = improved(s, best_s)
        log.append((tag, cfg, res, s, keep))
        if keep:
            best, best_s = cfg, s
        return s

    step("R1", "+ 코드 점수", best.with_(rerank=True))
    step("R2", "+ 벡터·BM25 합치기", best.with_(retrieve="rrf"))
    if use_llm:
        before = best
        step("R3", "질문 재작성", before.with_(query="rewrite"))
        step("R4", "HyDE", before.with_(query="hyde"))
    for t in THRESHOLDS:
        step("R5", f"+ 거리 임계값 {t}", best.with_(threshold=t))
    # MMR: 정답(Hit·Precision)이 줄지 않으면서 다양성이 오르면 남김
    for lam in MMR_LAMBDAS:
        cfg = best.with_(mmr=lam)
        res, s = try_(f"R6 + MMR λ={lam}", cfg)
        keep = (s.hits, round(s.precision, 6)) >= (best_s.hits, round(best_s.precision, 6)) and s.categories > best_s.categories
        log.append(("R6", cfg, res, s, keep))
        if keep:
            best, best_s = cfg, s
    step("R7", "+ 후보 늘리기", best.with_(expand=True))
    if use_llm and best.query == "rewrite":
        step("R8", "재작성(엄격)", best.with_(query="rewrite_strict"))
        step("R9", "재작성(엄격, 태그는 점수만)", best.with_(query="rewrite_strict_q"))
    return log, best, best_s


# ── 결과 저장 ───────────────────────────────────────────
def write_details(path: Path, corpus: Corpus, questions: list[Question], runs: list[list[QResult]]) -> None:
    qmap = {q.id: q for q in questions}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["실행", "질문", "종류", "질문 글", "순위", "레시피", "정답", "태그", "Claude 출력"])
        for res in runs:
            for r in res:
                for pos, (i, ok) in enumerate(zip(r.top, r.correct), start=1):
                    rec = corpus.recipes[i]
                    w.writerow([r.run, r.qid, r.qtype, qmap[r.qid].query, pos, rec.title, "O" if ok else "X",
                                ", ".join(rec.tags), r.note if pos == 1 else ""])
                if not r.top:
                    w.writerow([r.run, r.qid, r.qtype, qmap[r.qid].query, "", "(결과 없음)", "X", "", r.note])


def summary_table(summaries: list[tuple[str, Summary, Optional[bool]]], n_by_type: dict) -> list[str]:
    lines = ["| 실행 | 재료형 Hit@3 | 문장형 Hit@3 | 합계 | Precision@3 | 결과 3개 미만 | 알레르기 위반 | 요리 종류 수 | Claude 호출 | 질문당 초 | 남김 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for run, s, keep in summaries:
        mark = {True: "✅", False: "—", None: "(참고)"}[keep]
        lines.append(
            f"| {run} | {s.hit.get('재료형', 0)}/{n_by_type.get('재료형', 0)} | {s.hit.get('문장형', 0)}/{n_by_type.get('문장형', 0)} "
            f"| **{s.hits}** | {s.precision:.2f} | {s.short} | {s.violations} | {s.categories:.2f} | {s.llm_calls} | {s.seconds:.2f} | {mark} |"
        )
    return lines


def changes(base: list[QResult], best: list[QResult], questions: list[Question]) -> list[str]:
    qmap = {q.id: q for q in questions}
    b = {r.qid: r for r in base}
    up = [r.qid for r in best if r.hit > b[r.qid].hit]
    down = [r.qid for r in best if r.hit < b[r.qid].hit]
    fmt = lambda ids: ", ".join(f"{i} {qmap[i].query}" for i in ids) or "없음"  # noqa: E731
    return [f"- 좋아진 질문 {len(up)}개: {fmt(up)}", f"- 나빠진 질문 {len(down)}개: {fmt(down)}"]


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="검색 전략 실험 (DB 없이)")
    p.add_argument("--all", action="store_true", help="R0 → R6 순서대로")
    p.add_argument("--config", default=None, help='조합 하나만, 예: "rewrite,rrf,rerank,mmr=0.7"')
    p.add_argument("--no-llm", action="store_true", help="Claude 를 부르지 않음 (재작성·HyDE 건너뜀)")
    p.add_argument("--only", default=None, help="질문 번호만, 예: I01,Q01")
    p.add_argument("--questions", type=Path, default=QUESTIONS)
    p.add_argument("--seed", type=Path, default=SEED)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)
    if not args.all and not args.config:
        p.error("--all 또는 --config 중 하나를 주세요")

    questions = load_questions(args.questions)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        questions = [q for q in questions if q.id in wanted]
    corpus = load_corpus(args.seed)
    outside = Outside(args.out, use_llm=not args.no_llm)
    n_by_type: dict = {}
    for q in questions:
        n_by_type[q.type] = n_by_type.get(q.type, 0) + 1
    print(f"레시피 {len(corpus.recipes)}개, 질문 {len(questions)}개")

    if args.config:
        cfg = parse_config(args.config)
        res = run_config(cfg.name(), cfg, corpus, questions, outside)
        s = summarize(cfg.name(), res)
        print("\n".join(summary_table([(cfg.name(), s, None)], n_by_type)))
        write_details(args.out / "details_single.csv", corpus, questions, [res])
        return

    log, best, best_s = ablation(corpus, questions, outside, use_llm=not args.no_llm)
    write_details(args.out / "details.csv", corpus, questions, [res for _, _, res, _, _ in log])
    best_res = next(res for _, cfg, res, s, _ in log if s is best_s)
    md = [
        "# 검색 전략 실험 결과",
        "",
        f"- 레시피 {len(corpus.recipes)}개, 질문 {len(questions)}개 ({', '.join(f'{k} {v}' for k, v in n_by_type.items())})",
        "- 기준에서 한 번에 한 단계씩 바꾸고, Hit@3 합(같으면 Precision@3)이 오를 때만 남겼어요. MMR 은 정답이 줄지 않으면서 요리 종류 수가 늘 때 남겼어요.",
        "- 모든 실행에서 알레르기·조리 시간은 먼저 걸러요 (앱과 같음).",
        "- Precision@3 = 맞은 개수 ÷ 3. 결과가 3개보다 적으면 빈자리는 틀린 것으로 셉니다.",
        "",
        *summary_table([(s.run, s, keep) for _, _, _, s, keep in log], n_by_type),
        "",
        f"## 최종 조합: {best.name()}",
        f"- Hit@3 {best_s.hits}/{len(questions)}, Precision@3 {best_s.precision:.2f}, 질문당 Claude {best_s.llm_calls / max(1, len(questions)):.1f}번",
        "",
        "## 기준(R0) → 최종 조합, 질문별 변화",
        *changes(log[0][2], best_res, questions),
        "",
    ]
    (args.out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n" + "\n".join(md))
    print(f"\n저장: {args.out / 'summary.md'}, {args.out / 'details.csv'}")


if __name__ == "__main__":
    main()
