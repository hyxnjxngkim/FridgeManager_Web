"""요리 후 평가 칸 (채팅·대시보드에서 같이 써요)."""
from __future__ import annotations

import streamlit as st

from lib.feedback import learn_from_comment, record_feedback
from lib.llm import get_client, llm_unavailable_reason

CHOICES = ["👍 좋았어요", "👎 별로였어요"]


def feedback_form(user_id: str, meal_log_id: str, title: str, key: str) -> bool:
    """평가를 저장하면 True. 코멘트가 있으면 Claude 가 취향으로 바꿔 기억해요."""
    with st.form(key, clear_on_submit=True):
        st.markdown(f"**{title}** 어땠어요?")
        choice = st.radio("평가", CHOICES, horizontal=True, index=None, label_visibility="collapsed")
        comment = st.text_input("한 줄 후기 (선택)", placeholder="예: 너무 매웠어요 / 아이가 잘 먹었어요", max_chars=200)
        if not st.form_submit_button("평가 남기기"):
            return False
    if choice is None:
        st.error("👍 또는 👎 를 골라 주세요.")
        return False
    rating = 1 if choice == CHOICES[0] else -1
    record_feedback(user_id, meal_log_id, rating, comment)
    learned = []
    if comment.strip() and llm_unavailable_reason() is None:
        learned = learn_from_comment(get_client(), user_id, title, rating, comment)
    msg = "평가를 남겼어요. 다음 추천에 반영할게요."
    if learned:
        msg += " 기억한 취향: " + ", ".join(learned)
    st.session_state.feedback_msg = msg
    return True
