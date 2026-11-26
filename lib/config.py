"""환경변수 읽기. 프로젝트 루트의 .env 파일을 사용합니다."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PG_HOST = os.getenv("PG_HOST", "")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "")
PG_USER = os.getenv("PG_USER", "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_SCHEMA = os.getenv("PG_SCHEMA", "fridge")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Phase 3: 레시피 (팀원 B)
RECIPE_API_KEY = os.getenv("RECIPE_API_KEY", "")  # 식품안전나라 Open API (시드 스크립트만 씀)
# 임베딩: Amazon Titan Text Embeddings V2 (Bedrock). RDS와 리전이 달라도 돼요.
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "")
EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
AWS_PROFILE = os.getenv("AWS_PROFILE", "")  # 로컬에서만. EC2는 비워 두면 서버 역할(IAM role)을 씀


def is_db_configured() -> bool:
    return bool(PG_HOST and PG_DB and PG_USER and PG_PASSWORD)
