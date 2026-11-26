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


def is_db_configured() -> bool:
    return bool(PG_HOST and PG_DB and PG_USER and PG_PASSWORD)
