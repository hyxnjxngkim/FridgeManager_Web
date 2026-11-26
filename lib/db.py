"""PostgreSQL(AWS RDS) 연결.

- 앱(Streamlit): fetch_all / fetch_one / execute 를 쓰세요. 연결 풀을 공유해요.
- 스크립트: connect() 로 연결 하나를 직접 열어요 (scripts/migrate.py).

⚠️ RLS(행 단위 보안)가 없으니, 사용자 데이터를 다루는 SQL에는
   반드시 "where user_id = %s" 조건을 붙이세요.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from lib.config import PG_DB, PG_HOST, PG_PASSWORD, PG_PORT, PG_SCHEMA, PG_USER


def conninfo() -> str:
    return make_conninfo(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        connect_timeout=10,
        application_name="fridge-manager",
        options=f"-c search_path={PG_SCHEMA},public",  # 테이블은 fridge, pgvector 는 public
    )


def connect() -> psycopg.Connection:
    """연결 하나 (스크립트용)."""
    return psycopg.connect(conninfo())


def _pool():
    # streamlit 은 앱에서만 필요해서 여기서 불러와요 (스크립트는 streamlit 없이도 동작)
    import streamlit as st
    from psycopg_pool import ConnectionPool

    @st.cache_resource(show_spinner=False)
    def make_pool() -> ConnectionPool:
        return ConnectionPool(
            conninfo(),
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            check=ConnectionPool.check_connection,  # 터널이 끊겼다 붙어도 다시 연결
            open=True,
        )

    return make_pool()


def fetch_all(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    with _pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
    with _pool().connection() as conn:
        return conn.execute(sql, params).fetchone()


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """여러 SQL을 한 번에 — 블록 안에서 오류가 나면 전부 취소돼요."""
    with _pool().connection() as conn:
        with conn.transaction():
            yield conn


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """INSERT/UPDATE/DELETE. 바뀐 행 수를 돌려줘요. (블록이 끝나면 자동 커밋)"""
    with _pool().connection() as conn:
        return conn.execute(sql, params).rowcount
