import streamlit as st

from lib.ui import coming_soon

st.title("냉장고 에이전트")
st.caption("무엇을 만들지 물어보세요.")
coming_soon(
    "Phase 4",
    ["임박 재료 우선 레시피 추천 (출처 포함)", '"이거 만들게" → 재고 자동 차감', "취향·알레르기 기억"],
)
