"""설정 — 기억한 취향·알레르기 보기/추가/삭제 (Phase 4)."""
import streamlit as st

from lib.auth import require_user
from lib.preferences import KIND_LABELS, delete_preference_by_id, get_preferences, save_preference

user = require_user()

st.title("설정")
st.caption(user.email)

st.subheader("기억한 취향·알레르기")
st.caption("채팅에서 말하면 에이전트가 저장해요. 여기서 직접 추가하거나 지울 수도 있어요. 알레르기 재료가 든 레시피는 추천에서 빠져요.")

prefs = get_preferences(user.id)
if not prefs:
    st.info("아직 기억한 게 없어요.")
for kind, label in KIND_LABELS.items():
    items = [p for p in prefs if p.kind == kind]
    if not items:
        continue
    st.markdown(f"**{label}**")
    for p in items:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"- {p.value}")
        if c2.button("삭제", key=f"del-{p.id}"):
            delete_preference_by_id(user.id, p.id)
            st.rerun()

with st.form("add-pref", clear_on_submit=True):
    c1, c2 = st.columns([1, 2])
    kind = c1.selectbox("종류", list(KIND_LABELS), format_func=KIND_LABELS.get)
    value = c2.text_input("내용", placeholder="예: 땅콩, 매운맛, 다이어트")
    if st.form_submit_button("추가"):
        try:
            save_preference(user.id, kind, value)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
