"""냉장고를 부탁해 — 시작 파일.

실행: streamlit run app.py
로그인 여부를 확인하고, 메뉴(페이지 목록)를 만든 뒤 고른 페이지를 보여줍니다.
"""
import streamlit as st

from lib.auth import current_user, sign_out
from lib.config import is_supabase_configured

st.set_page_config(page_title="냉장고를 부탁해", page_icon="🧊", layout="wide")


def setup_notice() -> None:
    st.title("Supabase 설정이 필요해요")
    st.markdown(
        """
1. supabase.com에서 프로젝트를 만들어요.
2. `.env.example`을 `.env`로 복사하고 `SUPABASE_URL`, `SUPABASE_ANON_KEY`를 채워요.
3. SQL Editor에서 `supabase/migrations/`의 SQL 파일을 번호 순서대로 실행해요.
4. 앱을 다시 시작해요 (`streamlit run app.py`).
"""
    )


if not is_supabase_configured():
    setup_notice()
    st.stop()

user = current_user()

if user is None:
    nav = st.navigation([st.Page("views/login.py", title="로그인", icon="🔑")], position="hidden")
else:
    nav = st.navigation(
        {
            "": [st.Page("views/home.py", title="홈", icon="🏠", default=True)],
            "냉장고": [
                st.Page("views/inventory.py", title="재고", icon="🧊"),
                st.Page("views/upload.py", title="재료 등록", icon="📷"),
            ],
            "요리": [
                st.Page("views/chat.py", title="채팅", icon="💬"),
                st.Page("views/plan.py", title="이번 주 식단", icon="📋"),
                st.Page("views/calendar.py", title="달력", icon="📅"),
            ],
            "기록": [
                st.Page("views/dashboard.py", title="통계", icon="📊"),
                st.Page("views/settings.py", title="설정", icon="⚙️"),
            ],
        }
    )
    with st.sidebar:
        st.caption(f"로그인: {user.email}")
        if st.button("로그아웃", width="stretch"):
            sign_out()
            st.rerun()

nav.run()
