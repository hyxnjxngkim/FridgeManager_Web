"""임베딩 요청 모양과 시드 스크립트의 파일 흐름 검사 — Bedrock·DB 없이."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

import lib.embeddings as emb
from tests.test_recipe_import import ROW_28

ROOT = Path(__file__).resolve().parent.parent


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed_recipes", ROOT / "scripts" / "seed_recipes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeBedrock:
    def __init__(self, dim=emb.EMBED_DIM):
        self.dim, self.requests = dim, []

    def invoke_model(self, **kw):
        self.requests.append(kw)
        return {"body": io.BytesIO(json.dumps({"embedding": [0.5] * self.dim}).encode())}


# ── 임베딩 ──────────────────────────────────────────
def test_embed_text_sends_titan_v2_request():
    fake = FakeBedrock()
    vec = emb.embed_text("두부 된장국", client=fake)
    assert len(vec) == 1024
    req = fake.requests[0]
    assert req["modelId"] == "amazon.titan-embed-text-v2:0"
    assert json.loads(req["body"]) == {"inputText": "두부 된장국", "dimensions": 1024, "normalize": True}


def test_embed_text_rejects_wrong_dimension_and_empty_text():
    with pytest.raises(ValueError):
        emb.embed_text("두부", client=FakeBedrock(dim=256))
    with pytest.raises(ValueError):
        emb.embed_text("  ", client=FakeBedrock())


def test_to_pgvector():
    assert emb.to_pgvector([0.5, -0.25, 1e-8]) == "[0.5,-0.25,1e-08]"


# ── 시드: B 는 파일로, A 는 그 파일을 DB 로 ──────────────────
def test_dry_run_writes_embedded_file_and_load_reads_it(tmp_path, monkeypatch):
    seed = _load_seed()
    monkeypatch.setattr(emb, "embed_text", lambda text, client=None: [0.1] * emb.EMBED_DIM)
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(json.dumps([ROW_28, dict(ROW_28, RCP_SEQ="29", RCP_PARTS_DTLS="")]), encoding="utf-8")
    out = tmp_path / "seed.jsonl.gz"

    seed.main(["--dry-run", "--from-json", str(rows_file), "--out", str(out)])

    items = list(seed.read_seed_file(out))
    assert len(items) == 1  # 재료가 빈 29번은 건너뜀
    row, vec = items[0]
    assert row["source_id"] == "foodsafety:28" and row["title"] == "새우 두부 계란찜"
    assert row["ingredients"][0] == {"name": "연두부", "qty": 75.0, "unit": "g", "optional": False}
    assert len(vec) == 1024


def test_load_file_upserts_into_db(tmp_path, monkeypatch):
    seed = _load_seed()
    out = tmp_path / "seed.jsonl"
    row = {"source_id": "foodsafety:28", "title": "t", "ingredients": [], "steps": "s", "cook_minutes": 10,
           "servings": 1, "tags": [], "allergens": [], "image_url": None, "embedding": [0.1] * emb.EMBED_DIM}
    out.write_text(json.dumps(row) + "\n", encoding="utf-8")

    executed = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            executed.append((sql, params))
            return self

        def fetchone(self):
            return (0,)

        def commit(self):
            pass

    monkeypatch.setattr("lib.db.connect", lambda: FakeConn())
    seed.main(["--load-file", str(out)])
    upserts = [p for s, p in executed if "insert into recipes" in s]
    assert len(upserts) == 1
    assert "on conflict (source_id) do update" in seed.UPSERT_SQL
    assert upserts[0][0] == "foodsafety:28" and upserts[0][-1].startswith("[0.1,")


def test_load_file_rejects_rows_without_embedding(tmp_path):
    seed = _load_seed()
    out = tmp_path / "seed.jsonl"
    out.write_text(json.dumps({"source_id": "x", "embedding": None}) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        list(seed.read_seed_file(out))
