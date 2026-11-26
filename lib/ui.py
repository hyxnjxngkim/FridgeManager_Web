"""여러 페이지에서 같이 쓰는 화면 조각."""
from __future__ import annotations

import streamlit as st

from lib.dates import d_day_label, expiry_level
from lib.models import RecipeIngredient, RecipeMatch

LEVEL_EMOJI = {"expired": "⚫", "urgent": "🔴", "soon": "🟠", "ok": "🟢"}


def expiry_label(days_left: int) -> str:
    """예: '🔴 D-1', '🟠 D-3', '⚫ 2일 지남'"""
    return f"{LEVEL_EMOJI[expiry_level(days_left)]} {d_day_label(days_left)}"


def coming_soon(phase: str, items: list[str]) -> None:
    with st.container(border=True):
        st.markdown(f"**{phase}에서 만들 기능** · 지금은 빈 화면이에요.")
        st.markdown("\n".join(f"- {item}" for item in items))


# ── 레시피 카드 (Phase 3, 팀원 B) ─────────────────────────
RECIPE_DATA_CREDIT = "레시피 데이터: 식품안전나라"  # 공공누리 출처표시 (레시피별 출처는 없음)


def recipe_data_credit() -> None:
    """레시피를 보여 주는 화면 아래에 한 줄 (홈, 채팅 등)."""
    st.caption(RECIPE_DATA_CREDIT)


def _ingredient_text(ing: RecipeIngredient) -> str:
    """예: '연두부 75g', '시금치 10g(선택)', '소금'"""
    qty = ""
    if ing.qty is not None:
        qty = f"{ing.qty:g}{ing.unit or ''}"
    text = f"{ing.name} {qty}".strip()
    return f"{text}(선택)" if ing.optional else text


def recipe_card(match: RecipeMatch) -> None:
    """레시피 카드 하나를 그려요. 홈(B)과 채팅(A)이 같이 써요.

    보여 주기만 해요. "이거 만들게" 같은 버튼은 부르는 쪽에서 카드 아래에 따로 붙여요.
    """
    r = match.recipe
    with st.container(border=True):
        if r.image_url:
            st.image(r.image_url, width="stretch")
        st.markdown(f"**{r.title}**")

        info = []
        if r.cook_minutes is not None:
            info.append(f"⏱ 약 {r.cook_minutes}분 (추정)")
        if r.servings:
            info.append(f"{r.servings}인분")
        if info:
            st.caption(" · ".join(info))

        if match.uses_expiring:
            st.markdown("🛟 구출 재료: " + ", ".join(f"`{name}`" for name in match.uses_expiring))
        if match.missing:
            st.markdown("🛒 없는 재료: " + ", ".join(match.missing))

        st.markdown("재료: " + ", ".join(_ingredient_text(i) for i in r.ingredients))

        if r.allergens:
            st.caption("⚠️ 알레르기 성분: " + ", ".join(r.allergens) + " · 드시기 전에 꼭 확인하세요")

        with st.expander("만드는 법"):
            st.markdown(r.steps)
