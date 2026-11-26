import streamlit as st

from lib.ui import coming_soon

st.title("재료 등록")
st.caption("영수증이나 냉장고 사진을 올리면 재료를 뽑아줘요.")
coming_soon(
    "Phase 2",
    ["영수증 인식 (Claude Haiku)", "냉장고 사진 인식 (Claude Sonnet)", "인식 결과 확인·수정 후 저장"],
)
