import streamlit as st

from lib.ui import coming_soon

st.title("통계")
st.caption("얼마나 구출했는지 확인해요.")
coming_soon(
    "Phase 6",
    ["구출한 재료 수 / 버린 재료 수 / 구출률", "주별 구출 vs 폐기 차트", "자주 먹은 요리 TOP 5"],
)
