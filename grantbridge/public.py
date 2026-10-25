"""Shared furniture for GrantBridge's public website.

The public site is five pages — Home, About Us, Try Features, How It Works, and Trust & Responsible AI — plus Sign
in and Get started. They are registered with `st.navigation(..., position="top")` in `streamlit_app.py`, so every
one of them carries the same horizontal bar across the top, with the current page marked. This module holds what
they share: the frame, the calls to action, and the footer. Each page keeps its own layout.

Safe by construction: nothing here reads an account's data. The only personal fact a public page uses is whether
someone is signed in, which decides where a call to action points.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
HERO_PHOTO = ASSETS / "photos" / "community-planning-1200.webp"
PREVIEW = ASSETS / "previews" / "workspace-preview.webp"

HOME = "app_pages/about.py"            # the Home page (kept at this path so existing links and scripts still work)
ABOUT_US = "app_pages/about_us.py"
TRY_FEATURES = "app_pages/try_features.py"
HOW_IT_WORKS = "app_pages/how_it_works.py"
TRUST = "app_pages/trust.py"
SIGN_IN = "app_pages/sign_in.py"
PUBLIC_PAGES = (HOME, ABOUT_US, TRY_FEATURES, HOW_IT_WORKS, TRUST, SIGN_IN)
# (title, description, destination) for the "explore" cards on Home.
EXPLORE = (
    ("Our Story", "Why we believe smaller nonprofits deserve better tools to pursue funding.", ABOUT_US),
    ("Experience GrantBridge", "Try an interactive grant assessment and see how decisions change.", TRY_FEATURES),
    ("How It Works", "Follow the journey from finding funding to preparing a stronger application.", HOW_IT_WORKS),
    ("Built on Trust", "Explore our approach to transparency, responsible AI, and human oversight.", TRUST),
)

PHOTO_ALT = ("A small community team plans together around a wooden table covered with handwritten notes and sketches, "
             "in a bright room with natural light.")
PHOTO_CREDIT = ("Photo: [Sweet Life on Unsplash](https://unsplash.com/photos/people-are-brainstorming-and-working-"
                "together-on-papers-57XMk9_A4fo) (Unsplash License). The people shown are not affiliated with "
                "GrantBridge.")
PREVIEW_ALT = ("A GrantBridge screen with the sample organization's data: the Can we afford to win? check for a "
               "SAMPLE grant, with the match needed, the cash tied up at the worst point, and a chart of cash over "
               "the grant.")
# One restrained line in the footer. The full picture — what is implemented, what is not, and what a visitor
# should not rely on yet — lives on the Trust & Responsible AI page, one click away from every page.
FOOTER_NOTE = ("GrantBridge is in active development and is not yet intended for confidential information. "
               "Sample opportunities are labelled throughout. See Trust & Responsible AI for the detail.")


def go(user, page: str, tab: str | None = None) -> None:
    """Follow a link. A visitor can only reach the public pages, so a private destination becomes the sign-up form."""
    if user is None:
        st.session_state["auth_tab"] = tab or "Create account"
        st.switch_page(SIGN_IN)
    st.switch_page(page)


@contextmanager
def shell(name: str):
    """Open a public page: the shared frame (ivory field, serif headings, centred measure), then the footer."""
    with st.container(key="about-page"):  # the key the public stylesheet hangs off
        with st.container(key=f"public-{name}"):
            yield
        footer()


def eyebrow(key: str, text: str) -> None:
    """The small capitalised label above a section heading."""
    with st.container(key=f"about-eyebrow-{key}"):
        st.markdown(text)


def lede(text: str) -> None:
    """The larger paragraph that follows a page's title."""
    with st.container(key="about-lede"):
        st.markdown(text)


def visitor_actions(user, key: str) -> None:
    """Get started / Create an account / Sign in, in that order, on every public page."""
    with st.container(horizontal=True, key=f"about-cta-{key}"):
        if st.button("Get started", key=f"about_start_{key}", type="primary", icon=":material/arrow_forward:"):
            go(user, SIGN_IN, "Create account")
        if st.button("Create an account", key=f"about_create_{key}", icon=":material/person_add:"):
            go(user, SIGN_IN, "Create account")
        if st.button("Sign in", key=f"about_signin_{key}", icon=":material/login:", type="tertiary"):
            go(user, SIGN_IN, "Log in")


def member_actions(user, key: str) -> None:
    with st.container(horizontal=True, key=f"about-cta-{key}"):
        if st.button("Find grants", key=f"about_find_{key}", type="primary", icon=":material/travel_explore:"):
            go(user, "app_pages/find_grants.py")
        if st.button("Build your organization profile", key=f"about_profile_{key}", icon=":material/apartment:"):
            go(user, "app_pages/profile.py")


def closing(user, where: str, heading: str, text: str, secondary: tuple[str, str] | None = None) -> None:
    """The dark band every public page ends with: one clear next step, and at most one alternative."""
    st.space("medium")
    # Home's band keeps the "about-closing" key: the capture and browser scripts wait on it.
    with st.container(key="about-closing" if where in ("home", "closing") else f"public-closing-{where}"):
        st.markdown(f"### {heading}")
        st.markdown(text)
        if user is None:
            suffix = where if where == "closing" else f"{where}-closing"
            with st.container(horizontal=True, key=f"about-cta-{suffix}"):
                if st.button("Get started", key=f"about_start_{suffix}", type="primary",
                             icon=":material/arrow_forward:"):
                    go(user, SIGN_IN, "Create account")
                if secondary is not None:
                    label, target = secondary
                    if st.button(label, key=f"about_create_{suffix}", icon=":material/play_circle:",
                                 type="tertiary"):
                        st.switch_page(target)
                elif st.button("Create an account", key=f"about_create_{suffix}", icon=":material/person_add:"):
                    go(user, SIGN_IN, "Create account")
                if st.button("Sign in", key=f"about_signin_{suffix}", icon=":material/login:", type="tertiary"):
                    go(user, SIGN_IN, "Log in")
        else:
            member_actions(user, f"{where}-closing")


def footer() -> None:
    """The same footer on every public page: the other four pages, and what GrantBridge is."""
    st.space("medium")
    with st.container(key="public-footer"):
        cols = st.columns([2, 1, 1, 1])
        with cols[0]:
            st.markdown("**GrantBridge**")
            st.caption("Grant strategy for small nonprofits.")
        pairs = [(("Home", HOME), ("About Us", ABOUT_US)),
                 (("Try Features", TRY_FEATURES), ("How It Works", HOW_IT_WORKS)),
                 (("Trust & Responsible AI", TRUST), ("Sign in", SIGN_IN))]
        for col, links in zip(cols[1:], pairs):
            with col:
                for label, target in links:
                    st.page_link(target, label=label)
        st.caption(FOOTER_NOTE)
