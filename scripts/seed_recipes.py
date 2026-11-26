"""레시피 시드: 식품안전나라 Open API → Recipe 변환 → 임베딩(Titan V2) → recipes 표에 저장.

두 사람이 나눠서 해요 (B 는 DB 에 연결하지 않음)
    [B] python scripts/seed_recipes.py --dry-run --out db/seed/recipes_seed.jsonl.gz
        → API·변환·임베딩까지 해서 파일로 (DB 필요 없음, B 의 AWS 계정으로 임베딩)
    [A] python scripts/seed_recipes.py --load-file db/seed/recipes_seed.jsonl.gz
        → 그 파일을 DB 에 넣기만 (API 키·Bedrock 필요 없음, 로컬은 터널 먼저)

한 사람이 한 번에 할 때
    python scripts/seed_recipes.py                      # API → 변환 → 임베딩 → DB

그 밖의 옵션
    --dry-run --no-embed   임베딩도 빼고 변환만 확인
    --limit 20             앞에서 20개만
    --from-json rows.json  API 대신 저장해 둔 응답(row 배열) 사용

필요한 .env 값
    RECIPE_API_KEY  식품안전나라 키 (--from-json, --load-file 이면 필요 없음)
    BEDROCK_REGION  Titan V2 가 있는 리전, AWS_PROFILE(로컬만)  (--no-embed, --load-file 이면 필요 없음)
    PG_*            DB 접속 (--dry-run 이면 필요 없음)

임베딩은 계정이 달라도 같은 모델(Titan V2, 1024차원, 정규화)이면 같은 숫자라서,
시드는 B 계정, 검색은 A 계정이어도 돼요.

source_id('foodsafety:<번호>')로 upsert 해서, 다시 실행해도 레시피 수가 늘지 않아요.
db/0003_recipes.sql 이 먼저 실행돼 있어야 해요 (python scripts/migrate.py).
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path
from typing import Iterator, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import RECIPE_API_KEY  # noqa: E402
from lib.recipe_import import embedding_text, recipe_to_row, row_to_recipe  # noqa: E402

API_URL = "http://openapi.foodsafetykorea.go.kr/api/{key}/COOKRCP01/json/{start}/{end}"
PAGE = 1000  # 한 번에 받을 수 있는 최대 개수
DEFAULT_OUT = ROOT / "data" / "recipes_preview.jsonl"

UPSERT_SQL = """
insert into recipes
  (source_id, title, ingredients, steps, cook_minutes, servings, tags, allergens, image_url, embedding)
values (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::vector)
on conflict (source_id) do update set
  title = excluded.title, ingredients = excluded.ingredients, steps = excluded.steps,
  cook_minutes = excluded.cook_minutes, servings = excluded.servings, tags = excluded.tags,
  allergens = excluded.allergens, image_url = excluded.image_url, embedding = excluded.embedding
"""


# ── 1) 가져오기 ─────────────────────────────────────
def fetch_rows(key: str, limit: Optional[int] = None) -> Iterator[dict]:
    """API 에서 row 를 차례로 (1~1000, 1001~2000, …). 키는 어디에도 출력하지 않아요."""
    if not key:
        sys.exit(".env 에 RECIPE_API_KEY 를 넣어 주세요 (또는 --from-json 사용).")
    start, sent = 1, 0
    while True:
        end = start + PAGE - 1
        if limit is not None:
            end = min(end, start + (limit - sent) - 1)
        url = API_URL.format(key=key, start=start, end=end)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                body = json.loads(r.read().decode("utf-8"))["COOKRCP01"]
        except Exception as e:  # 키가 든 주소는 출력하지 않아요
            sys.exit(f"레시피 API 요청 실패 ({start}~{end}): {type(e).__name__}: {str(e).replace(key, '{KEY}')}")
        code = body.get("RESULT", {}).get("CODE", "")
        if code not in ("INFO-000", "INFO-200"):
            sys.exit(f"레시피 API 오류 {code}: {body.get('RESULT', {}).get('MSG', '')}")
        rows = body.get("row") or []
        total = int(body.get("total_count") or 0)
        print(f"  API {start}~{end}: {len(rows)}개 (전체 {total}개)")
        for row in rows:
            yield row
            sent += 1
            if limit is not None and sent >= limit:
                return
        start = end + 1
        if not rows or start > total:
            return


def load_rows(path: Path, limit: Optional[int]) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["COOKRCP01"]["row"] if isinstance(data, dict) else data
    return rows[:limit] if limit is not None else rows


# ── 2) 변환 + 3) 임베딩 ──────────────────────────────
def build(rows, embed: bool) -> Iterator[tuple[dict, Optional[list[float]]]]:
    from lib.embeddings import embed_text

    skipped = 0
    for row in rows:
        recipe = row_to_recipe(row)
        if recipe is None:
            skipped += 1
            continue
        vec = None
        if embed:
            try:
                vec = embed_text(embedding_text(recipe))
            except Exception as e:
                sys.exit(
                    f"임베딩 실패 ({recipe.id} {recipe.title}): {type(e).__name__}: {e}\n"
                    "→ .env 의 BEDROCK_REGION(Titan V2 가 있는 리전), AWS 로그인/서버 역할의 "
                    "bedrock:InvokeModel 권한을 확인해 주세요."
                )
        yield recipe_to_row(recipe), vec
    if skipped:
        print(f"  재료나 조리 순서가 비어 있어 건너뛴 레시피: {skipped}개")


# ── 4) 저장 ─────────────────────────────────────────
def save_to_db(items) -> None:
    from lib.db import connect
    from lib.embeddings import to_pgvector

    with connect() as conn:
        before = conn.execute("select count(*) from recipes where source_id like 'foodsafety:%'").fetchone()[0]
        n = 0
        for row, vec in items:
            conn.execute(
                UPSERT_SQL,
                (
                    row["source_id"], row["title"], json.dumps(row["ingredients"], ensure_ascii=False),
                    row["steps"], row["cook_minutes"], row["servings"], row["tags"], row["allergens"],
                    row["image_url"], to_pgvector(vec) if vec is not None else None,
                ),
            )
            n += 1
            if n % 100 == 0:
                conn.commit()
                print(f"  저장 {n}개…")
        conn.commit()
        after = conn.execute("select count(*) from recipes where source_id like 'foodsafety:%'").fetchone()[0]
    print(f"레시피 {n}개 저장 (새로 {after - before}개, 갱신 {n - (after - before)}개). 지금 레시피 수: {after}개")


def _open(path: Path, mode: str):
    """'.gz' 로 끝나면 압축 파일로 읽고 써요."""
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def save_to_file(items, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = embedded = 0
    with _open(out, "w") as f:
        for row, vec in items:
            emb = [round(x, 6) for x in vec] if vec is not None else None
            f.write(json.dumps({**row, "embedding": emb}, ensure_ascii=False) + "\n")
            n += 1
            embedded += emb is not None
    print(f"[dry-run] 레시피 {n}개(임베딩 {embedded}개)를 {out} 에 저장했어요 (DB 에는 저장하지 않음).")


def read_seed_file(path: Path) -> Iterator[tuple[dict, list[float]]]:
    """--dry-run 으로 만든 파일 → (row, embedding). 임베딩이 없거나 차원이 다르면 멈춰요."""
    from lib.embeddings import EMBED_DIM

    with _open(path, "r") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            vec = row.pop("embedding", None)
            if not vec or len(vec) != EMBED_DIM:
                sys.exit(f"{path} {line_no}번째 줄({row.get('source_id')}): 임베딩이 없거나 {EMBED_DIM}차원이 아니에요.")
            yield row, vec


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="식품안전나라 레시피를 recipes 표에 넣어요.")
    p.add_argument("--dry-run", action="store_true", help="DB 대신 파일로 저장")
    p.add_argument("--no-embed", action="store_true", help="임베딩 생략 (dry-run 에서만)")
    p.add_argument("--limit", type=int, default=None, help="앞에서 N개만")
    p.add_argument("--from-json", type=Path, default=None, help="API 대신 저장해 둔 응답 파일")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="dry-run 결과 파일 (.gz 면 압축)")
    p.add_argument("--load-file", type=Path, default=None, help="dry-run 결과 파일을 DB 에 넣기만")
    args = p.parse_args(argv)

    if args.load_file:
        if args.dry_run or args.from_json or args.no_embed:
            sys.exit("--load-file 은 다른 옵션 없이 써요.")
        save_to_db(read_seed_file(args.load_file))
        return
    if args.no_embed and not args.dry_run:
        sys.exit("--no-embed 는 --dry-run 과 함께만 써요 (DB 레시피에는 임베딩이 있어야 검색돼요).")

    rows = load_rows(args.from_json, args.limit) if args.from_json else fetch_rows(RECIPE_API_KEY, args.limit)
    items = build(rows, embed=not args.no_embed)
    if args.dry_run:
        save_to_file(items, args.out)
    else:
        save_to_db(items)


if __name__ == "__main__":
    main()
