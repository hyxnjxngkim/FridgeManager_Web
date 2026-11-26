import streamlit as st

from lib.auth import current_user
from lib.ui import coming_soon

st.title("설정")
user = current_user()
if user:
    st.caption(user.email)
coming_soon("Phase 4", ["기억한 취향·알레르기 보기 / 삭제", "식단 목표 (다이어트, 고단백 등)"])
