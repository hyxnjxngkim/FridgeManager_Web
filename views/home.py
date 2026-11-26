import streamlit as st

from lib.auth import require_user
from lib.dates import today_kst
from lib.inventory import days_left, get_expiring
from lib.ui import coming_soon, expiry_label

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

coming_soon("Phase 3·4", ["구출 레시피 추천 카드 3개", "에이전트에게 바로 물어보는 입력창"])
