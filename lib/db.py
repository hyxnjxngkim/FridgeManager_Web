"""Supabase 클라이언트.

접속한 사람(브라우저 세션)마다 클라이언트를 따로 만들어 st.session_state 에 보관합니다.
로그인하면 그 사람의 토큰이 클라이언트에 실리고, DB의 RLS(행 단위 보안) 덕분에
본인 데이터만 읽고 쓸 수 있어요.
"""
import streamlit as st
from supabase import Client, create_client

from lib.config import SUPABASE_ANON_KEY, SUPABASE_URL


def get_client() -> Client:
    if "supabase" not in st.session_state:
        st.session_state.supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return st.session_state.supabase
