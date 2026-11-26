"""이메일·비밀번호 로그인 (Supabase Auth)."""
from __future__ import annotations

from typing import Optional

import streamlit as st

from lib.db import get_client


def current_user():
    """로그인한 사용자 (없으면 None)."""
    return st.session_state.get("user")


def sign_in(email: str, password: str) -> Optional[str]:
    """성공하면 None, 실패하면 오류 메시지."""
    if not email or not password:
        return "이메일과 비밀번호를 입력해 주세요."
    try:
        res = get_client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        return "로그인에 실패했어요. 이메일과 비밀번호를 확인해 주세요. (가입 확인 메일을 눌렀는지도 확인해 주세요)"
    st.session_state.user = res.user
    return None


def sign_up(email: str, password: str) -> tuple[Optional[str], Optional[str]]:
    """(오류 메시지, 안내 메시지)를 돌려줍니다."""
    if not email or not password:
        return "이메일과 비밀번호를 입력해 주세요.", None
    if len(password) < 6:
        return "비밀번호는 6자 이상이어야 해요.", None
    try:
        res = get_client().auth.sign_up({"email": email, "password": password})
    except Exception as e:  # 이미 가입된 이메일 등
        return f"가입하지 못했어요: {e}", None

    if res.session:  # Supabase에서 이메일 확인을 꺼 둔 경우 바로 로그인됨
        st.session_state.user = res.user
        return None, None
    return None, "확인 메일을 보냈어요. 메일의 링크를 누른 뒤 로그인해 주세요."


def sign_out() -> None:
    try:
        get_client().auth.sign_out()
    except Exception:
        pass
    for key in ("user", "supabase"):
        st.session_state.pop(key, None)
