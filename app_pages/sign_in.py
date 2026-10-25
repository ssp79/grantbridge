"""Sign up / Log in."""

from pathlib import Path

import streamlit as st

from grantbridge import auth, session, validation

ICON = Path(__file__).resolve().parents[1] / "assets" / "logo-icon.svg"

flash = session.pop_flash()

left, center, right = st.columns([1, 1.6, 1])
with center:
    st.image(str(ICON), width=56)
    st.title("GrantBridge", anchor=False)
    st.markdown("**Find grants that fit your nonprofit, see exactly what still needs checking, and draft "
                "answers from your own facts.**")
    st.caption(
        "Course demo for small U.S. nonprofits. Use sample information only. "
        "This demo does not have production-grade security."
    )
    if flash:
        st.info(flash, icon=":material/info:")
    st.page_link("app_pages/about.py", label="New here? See what GrantBridge does", icon=":material/info:")

    card = st.container(border=True, key="card-auth")
    # The About page's "Create an account" and "Sign in" buttons choose the tab that opens first.
    wanted = st.session_state.get("auth_tab")
    log_in_tab, sign_up_tab = card.tabs(["Log in", "Create account"],
                                        default=wanted if wanted in ("Log in", "Create account") else None)

    with log_in_tab:
        with st.form("log_in", clear_on_submit=False, border=False):
            email = st.text_input("Email", autocomplete="email", max_chars=254)
            password = st.text_input(
                "Password", type="password", autocomplete="current-password",
                max_chars=validation.PASSWORD_MAX,
            )
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            try:
                user = auth.log_in(email, password)
            except auth.AuthError as err:
                st.error(str(err), icon=":material/error:")
            else:
                session.start(user)
                st.rerun()
        with st.expander("Forgot your password?"):
            st.markdown(
                "This course demo cannot email you a reset link, so it never asks for your email here and never "
                "says whether an account exists. You can create a new account with a different email, or ask "
                "whoever runs this GrantBridge server to recreate yours with "
                "`python -m scripts.create_demo_account --email <address> --reset`. That deletes the account's "
                "data and prints a new one-time password."
            )

    with sign_up_tab:
        with st.form("sign_up", clear_on_submit=False, border=False):
            org_name = st.text_input("Organization name", max_chars=200)
            new_email = st.text_input("Email", autocomplete="email", max_chars=254, key="su_email")
            new_password = st.text_input(
                "Password", type="password", autocomplete="new-password",
                max_chars=validation.PASSWORD_MAX, key="su_pw",
                help=f"At least {validation.PASSWORD_MIN} characters. A short phrase works well.",
            )
            confirm = st.text_input(
                "Confirm password", type="password", autocomplete="new-password",
                max_chars=validation.PASSWORD_MAX, key="su_pw2",
            )
            st.caption(f"Passwords need at least {validation.PASSWORD_MIN} characters. Use sample organization "
                       "details: this is a demo.")
            created = st.form_submit_button("Create account", type="primary", width="stretch")
        if created:
            if new_password != confirm:
                st.error("The two passwords do not match.", icon=":material/error:")
            else:
                try:
                    user = auth.sign_up(new_email, new_password, org_name)
                except (auth.AuthError, validation.ValidationError) as err:
                    st.error(str(err), icon=":material/error:")
                else:
                    session.start(user)
                    st.rerun()
