"""글 → 숫자 1024개 (임베딩). Amazon Titan Text Embeddings V2, Bedrock (Phase 3, 팀원 B).

- 시드(scripts/seed_recipes.py)와 검색(lib/recipes.py)이 **같은 모델·같은 차원**을 써야 해요.
- 자격 증명: 로컬은 .env 의 AWS_PROFILE(aws login), EC2는 서버 역할(IAM role)의 bedrock:InvokeModel 권한.
- 리전: .env 의 BEDROCK_REGION. Titan V2 가 있는 리전이어야 해요 (RDS 리전과 달라도 됨).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional, Sequence

from lib.config import AWS_PROFILE, BEDROCK_REGION, EMBED_MODEL_ID

EMBED_DIM = 1024  # db/0001_init.sql 의 vector(1024) 와 같아야 해요
_MAX_CHARS = 20000  # Titan V2 입력 한도(8,192 토큰)보다 넉넉히 작게


@lru_cache(maxsize=1)
def _client() -> Any:
    import boto3  # 테스트·화면에서 임베딩을 안 쓸 때는 불러오지 않아요

    session = boto3.Session(profile_name=AWS_PROFILE or None, region_name=BEDROCK_REGION or None)
    return session.client("bedrock-runtime")


def embed_text(text: str, client: Optional[Any] = None) -> list[float]:
    """글 하나 → 숫자 1024개 (크기 1로 정규화). 실패하면 예외."""
    text = (text or "").strip()[:_MAX_CHARS]
    if not text:
        raise ValueError("임베딩할 글이 비어 있어요.")
    body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True})
    resp = (client or _client()).invoke_model(
        modelId=EMBED_MODEL_ID, body=body, contentType="application/json", accept="application/json"
    )
    vec = json.loads(resp["body"].read())["embedding"]
    if len(vec) != EMBED_DIM:
        raise ValueError(f"임베딩 차원이 {len(vec)}이에요 ({EMBED_DIM}이어야 해요).")
    return [float(x) for x in vec]


@lru_cache(maxsize=256)
def embed_query(text: str) -> tuple[float, ...]:
    """검색어 임베딩 (같은 검색어는 다시 부르지 않게 기억해 둬요)."""
    return tuple(embed_text(text))


def to_pgvector(vec: Sequence[float]) -> str:
    """psycopg 에 넘길 pgvector 글자 모양: '[0.1,0.2,…]' (SQL 에서 %s::vector 로 써요)."""
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
