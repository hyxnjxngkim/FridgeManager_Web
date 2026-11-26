"""여러 페이지에서 같이 쓰는 화면 조각."""
from __future__ import annotations

import streamlit as st

from lib.dates import d_day_label, expiry_level

LEVEL_EMOJI = {"expired": "⚫", "urgent": "🔴", "soon": "🟠", "ok": "🟢"}


def expiry_label(days_left: int) -> str:
    """예: '🔴 D-1', '🟠 D-3', '⚫ 2일 지남'"""
    return f"{LEVEL_EMOJI[expiry_level(days_left)]} {d_day_label(days_left)}"


def coming_soon(phase: str, items: list[str]) -> None:
    with st.container(border=True):
        st.markdown(f"**{phase}에서 만들 기능** · 지금은 빈 화면이에요.")
        st.markdown("\n".join(f"- {item}" for item in items))
