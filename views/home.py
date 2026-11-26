import streamlit as st

from lib.auth import require_user
from lib.dates import today_kst
from lib.inventory import days_left, get_expiring
from lib.recipes import search_recipes
from lib.ui import expiry_label, recipe_card, recipe_data_credit

HOME_RECIPES = 3  # 홈에 보여 줄 추천 레시피 수

st.title("오늘 구해야 할 재료")
st.caption("3일 안에 유통기한이 끝나는 재료예요.")

user = require_user()
today = today_kst()
items = get_expiring(user.id, 3, include_expired=True)
rescue = [i for i in items if days_left(i, today) >= 0]
expired = [i for i in items if days_left(i, today) < 0]

with st.container(border=True):
    if rescue:
        st.subheader(f"구출이 필요한 재료 {len(rescue)}개")
        st.markdown(
            "  ".join(f"`{i.name}` {expiry_label(days_left(i, today))}" for i in rescue)
        )
    else:
        st.subheader("임박한 재료가 없어요 🎉")
        st.caption("냉장고가 안전해요.")

    if expired:
        st.warning(
            f"유통기한이 지난 재료 {len(expired)}개가 있어요: "
            + ", ".join(i.name for i in expired)
        )
    st.page_link("views/inventory.py", label="재고 보기 →")

# ── 구출 레시피 추천 (Phase 3) ───────────────────────────
st.subheader("구출 레시피")
if not rescue:
    st.caption("임박한 재료가 생기면 그 재료로 만들 레시피를 추천해 드려요.")
else:
    matches = None
    try:
        with st.spinner("임박 재료로 만들 레시피를 찾고 있어요…"):
            matches = search_recipes(user.id, [i.name for i in rescue])[:HOME_RECIPES]
    except Exception:
        st.warning("레시피 추천을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
    if matches:
        for col, match in zip(st.columns(len(matches)), matches):
            with col:
                recipe_card(match)
    elif matches is not None:
        st.info("임박 재료로 만들 수 있는 레시피를 찾지 못했어요.")

recipe_data_credit()
