"""db/ 폴더의 SQL 파일을 번호 순서대로 한 번씩만 실행합니다.

사용법 (프로젝트 루트에서, 로컬이면 터널을 먼저 열고):
    python scripts/migrate.py           # 아직 안 한 파일 실행
    python scripts/migrate.py --status  # 무엇을 했는지만 보기

실행한 파일 이름은 schema_migrations 테이블에 기록돼요.
이미 실행한 파일은 고치지 말고, 바꿀 내용이 있으면 새 번호 파일을 만드세요.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.db import connect  # noqa: E402

MIGRATIONS = ROOT / "db"


def main() -> None:
    status_only = "--status" in sys.argv
    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))

    with connect() as conn:
        conn.execute(
            "create table if not exists schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        conn.commit()
        done = {r[0] for r in conn.execute("select name from schema_migrations").fetchall()}

        pending = [f for f in files if f.name not in done]
        for f in files:
            print(f"{'✓' if f.name in done else '·'} {f.name}")
        if status_only:
            return
        if not pending:
            print("모두 최신이에요.")
            return

        for f in pending:
            print(f"→ {f.name} 실행 중…")
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            print(f"  완료")


if __name__ == "__main__":
    main()
