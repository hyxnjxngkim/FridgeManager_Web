"""이메일·비밀번호 로그인 (users 테이블 + bcrypt)."""
from __future__ import annotations

import re
from typing import Optional

import psycopg
import streamlit as st

from lib.db import execute, fetch_one
from lib.models import AppUser
from lib.passwords import DUMMY_HASH, check_password_rules, hash_password, verify_password

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def current_user() -> Optional[AppUser]:
    """로그인한 사용자 (없으면 None)."""
    return st.session_state.get("user")


def require_user() -> AppUser:
    """페이지 맨 위에서 호출 — 로그인 안 했으면 페이지를 멈춰요."""
    user = current_user()
    if user is None:
        st.warning("로그인이 필요해요.")
        st.stop()
    return user


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def sign_in(email: str, password: str) -> Optional[str]:
    """성공하면 None, 실패하면 오류 메시지."""
    email = _normalize_email(email)
    if not email or not password:
        return "이메일과 비밀번호를 입력해 주세요."
    row = fetch_one("select id, email, password_hash from users where email = %s", (email,))
    ok = verify_password(password, row["password_hash"] if row else DUMMY_HASH)
    if not row or not ok:
        return "로그인에 실패했어요. 이메일과 비밀번호를 확인해 주세요."
    st.session_state.user = AppUser(id=str(row["id"]), email=row["email"])
    return None


def sign_up(email: str, password: str) -> Optional[str]:
    """성공하면 바로 로그인하고 None, 실패하면 오류 메시지."""
    email = _normalize_email(email)
    if not EMAIL_RE.match(email):
        return "이메일 형식이 올바르지 않아요."
    try:
        check_password_rules(password)
    except ValueError as e:
        return str(e)
    try:
        execute(
            "insert into users (email, password_hash) values (%s, %s)",
            (email, hash_password(password)),
        )
    except psycopg.errors.UniqueViolation:
        return "이미 가입된 이메일이에요. 로그인해 주세요."
    return sign_in(email, password)


def sign_out() -> None:
    # 채팅 기록 등 이 사람의 세션 데이터를 모두 지워요 (같은 브라우저에서 다른 계정이 로그인해도 안 보이게)
    st.session_state.clear()
