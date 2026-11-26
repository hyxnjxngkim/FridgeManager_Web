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

# Claude (AWS Bedrock, bedrock-runtime) — 이 AWS 계정에서 열려 있는 모델만 써요.
# - CLAUDE_MODEL: 채팅 에이전트 기본 모델. 비용을 아끼려고 Haiku 4.5.
# - CLAUDE_MODEL_SMART: 어려운 일에만 아껴 쓰는 모델 (Sonnet 4.6). Phase 4에서는 아직 안 씀.
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
CLAUDE_MODEL_SMART = os.getenv("CLAUDE_MODEL_SMART", "global.anthropic.claude-sonnet-4-6")


def is_db_configured() -> bool:
    return bool(PG_HOST and PG_DB and PG_USER and PG_PASSWORD)
