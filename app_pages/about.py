"""Home — the public landing page.

Deliberately short. The mission is on About Us, the working demonstrations on Try Features, the workflow on How It
Works, and the AI safeguards on Trust & Responsible AI. This page says what GrantBridge is for, shows one still of
the product, and points at the other four pages.

Public by design and safe by construction: it reads no account's data. The only personal fact it uses is whether
someone is signed in, which decides the calls to action.
"""

import streamlit as st

from grantbridge import components as c
from grantbridge import public, session

user = session.current_user()  # None for a visitor: never require_user on a public page

HEADLINE = "Less time chasing funding. More time changing lives."
SUPPORTING = ("Meet your AI-powered grant strategy partner. GrantBridge helps resource-constrained nonprofits "
              "discover funding opportunities, evaluate which grants are worth pursuing, develop stronger "
              "proposals, and make the most of limited staff time.")
PROMISES = ["Code decides; AI explains", "Unknown is never treated as ineligible", "Every AI answer checked by code",
            "Sample data for practice"]

with public.shell("home"):
    # ------------------------------------------------------------ hero: the promise, and a real team at work
    with st.container(key="about-hero"):
        text_col, photo_col = st.columns([11, 9], gap="large", vertical_alignment="center")
        with text_col:
            public.eyebrow("hero", "GrantBridge · Grant strategy for small nonprofits")
            st.title(HEADLINE, anchor=False)
            public.lede(SUPPORTING)
            if user is None:
                with st.container(horizontal=True, key="about-cta-hero"):
                    if st.button("Try GrantBridge", key="about_start_hero", type="primary",
                                 icon=":material/play_circle:"):
                        st.switch_page(public.TRY_FEATURES)
                    if st.button("How it works", key="about_create_hero", icon=":material/map:"):
                        st.switch_page(public.HOW_IT_WORKS)
                    if st.button("Sign in", key="about_signin_hero", icon=":material/login:", type="tertiary"):
                        public.go(user, public.SIGN_IN, "Log in")
            else:
                public.member_actions(user, "hero")
            st.caption("No account needed to try it · federal opportunities from Grants.gov")
        with photo_col, st.container(key="about-photo"):
            st.image(str(public.HERO_PHOTO), alt=public.PHOTO_ALT, width="stretch")
            st.caption(public.PHOTO_CREDIT)

    with st.container(horizontal=True, key="about-strip", gap="large"):
        for promise in PROMISES:
            st.caption(f":material/check: {promise}")

    # ------------------------------------------------------------ the one sentence that sets GrantBridge apart
    with st.container(key="about-positioning"):
        public.eyebrow("different", "What makes it different")
        st.markdown("### Most grant-writing tools help you apply. GrantBridge helps you decide what is worth "
                    "applying for.")
        st.markdown("Before your team spends days on an application, GrantBridge checks whether you are likely "
                    "eligible, whether the grant fits your mission, whether your staff has the hours, and whether "
                    "you could afford to win it.")

    # ------------------------------------------------------------ where to go next
    public.eyebrow("explore", "Explore GrantBridge")
    st.subheader("Discover what GrantBridge can do for you", anchor=False)
    st.markdown("Explore the tools, guidance, and principles behind smarter grant decisions.")
    st.space("small")
    for row in (public.EXPLORE[:2], public.EXPLORE[2:]):
        for col, (title, blurb, target) in zip(st.columns(2, gap="medium"), row):
            with col, st.container(border=True, key=f"explore-card-{c.slug(title)}", height="stretch"):
                st.page_link(target, label=title)
                st.caption(blurb)

    # ------------------------------------------------------------ a short trust line, with the detail one click away
    st.space("medium")
    with st.container(key="about-trustline"):
        st.markdown("#### Built to be checked, not taken on faith")
        st.markdown("Recommendations come from rules you can read, not from a model's opinion. AI drafts and "
                    "explains; every figure and quotation it produces is checked against your own records before "
                    "you see it, and anything unknown is labelled unknown rather than guessed.")
        if st.button("How we handle AI", key="home_go_trust_line", icon=":material/arrow_forward:", type="tertiary"):
            st.switch_page(public.TRUST)

    public.closing(user, "closing", "Ready to spend less time chasing funding?",
                   "Create your nonprofit profile and start finding opportunities worth pursuing.",
                   secondary=("Explore the interactive demo", public.TRY_FEATURES))
