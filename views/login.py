import streamlit as st

from lib.auth import sign_in, sign_up

_, center, _ = st.columns([1, 2, 1])
with center:
    st.title("🧊 냉장고를 부탁해")
    st.caption("버릴 뻔한 재료부터 맛있게 구출해요")

    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

    with login_tab:
        with st.form("login"):
            email = st.text_input("이메일", autocomplete="email")
            password = st.text_input("비밀번호", type="password", autocomplete="current-password")
            if st.form_submit_button("로그인", type="primary", width="stretch"):
                error = sign_in(email.strip(), password)
                if error:
                    st.error(error)
                else:
                    st.rerun()

    with signup_tab:
        with st.form("signup"):
            email = st.text_input("이메일", autocomplete="email")
            password = st.text_input(
                "비밀번호 (6자 이상)", type="password", autocomplete="new-password"
            )
            if st.form_submit_button("회원가입", width="stretch"):
                error, message = sign_up(email.strip(), password)
                if error:
                    st.error(error)
                elif message:
                    st.success(message)
                else:
                    st.rerun()
