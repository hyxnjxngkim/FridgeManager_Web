"""환경변수 읽기. 프로젝트 루트의 .env 파일을 사용합니다."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def is_supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)
