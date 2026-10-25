"""GrantBridge — Streamlit entry point.

Run with:  streamlit run streamlit_app.py

Signed-out visitors see the public website: Home, About Us, Try Features, How It Works,
Trust & Responsible AI, and Sign in, as a horizontal bar across the top of every one.
Every other page is registered with the router only once a user is logged in, and each
of those pages also calls session.require_user() itself.
"""

import logging
import uuid
from pathlib import Path

import streamlit as st

from grantbridge import db, logsafe, repo, session, ui

logsafe.install()  # every log line is scrubbed of secrets and email addresses
log = logging.getLogger("grantbridge")
ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="GrantBridge", page_icon=":material/handshake:", layout="wide")


@st.cache_resource
def _prepare_database(path: str, schema_version: str) -> bool:
    """Once per database file and schema version, so a server left running picks up new tables."""
    db.init_db()
    return True


_prepare_database(str(db.db_path()), db.schema_version())
ui.inject_css()

user = session.current_user()

ABOUT = "app_pages/about.py"  # the public Home page


def public_pages(default: str | None = None) -> list:
    """The public website, in the order it appears in the top bar. Home first, Sign in last."""
    return [
        st.Page(ABOUT, title="Home", icon=":material/home:", default=default == "home"),
        st.Page("app_pages/about_us.py", title="About Us", icon=":material/diversity_3:"),
        st.Page("app_pages/try_features.py", title="Try Features", icon=":material/play_circle:"),
        st.Page("app_pages/how_it_works.py", title="How It Works", icon=":material/map:"),
        st.Page("app_pages/trust.py", title="Trust & Responsible AI", icon=":material/verified_user:"),
        st.Page("app_pages/sign_in.py", title="Sign in", icon=":material/login:", default=default == "sign_in"),
    ]


st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "logo-icon.svg"), size="large")
if user is None:
    message_waiting = session.has_flash()  # "You have been logged out.": shown on the Sign in page
    page = st.navigation(public_pages(default="sign_in" if message_waiting else "home"), position="top")
else:
    page = st.navigation(
        {
            # Grouped in the order the work actually happens: get set up, decide what is worth pursuing, then
            # write it. Every page stays registered, so deep links and st.switch_page keep working from anywhere.
            "Workspace": [
                st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True),
                st.Page("app_pages/getting_started.py", title="Getting Started", icon=":material/school:"),
                st.Page("app_pages/advisor.py", title="AI Grant Advisor", icon=":material/forum:"),
            ],
            "Decide and plan": [
                st.Page("app_pages/find_grants.py", title="Find Grants", icon=":material/travel_explore:"),
                st.Page("app_pages/saved_grants.py", title="Saved Grants", icon=":material/bookmarks:"),
                st.Page("app_pages/pursue.py", title="Should We Pursue?", icon=":material/thumbs_up_down:"),
                st.Page("app_pages/portfolio.py", title="Portfolio Strategist", icon=":material/insights:"),
            ],
            "Draft and review applications": [
                st.Page("app_pages/applications.py", title="Applications", icon=":material/description:"),
            ],
            "Your organization": [
                st.Page("app_pages/setup.py", title="Set up", icon=":material/rocket_launch:"),
                st.Page("app_pages/profile.py", title="Organization Profile", icon=":material/apartment:"),
                st.Page("app_pages/settings.py", title="Account", icon=":material/account_circle:"),
            ],
            # The public pages stay reachable after signing in, so their links never dead-end.
            "The public site": [
                st.Page(ABOUT, title="Home", icon=":material/home:"),
                st.Page("app_pages/about_us.py", title="About Us", icon=":material/diversity_3:"),
                st.Page("app_pages/try_features.py", title="Try Features", icon=":material/play_circle:"),
                st.Page("app_pages/how_it_works.py", title="How It Works", icon=":material/map:"),
                st.Page("app_pages/trust.py", title="Trust & Responsible AI", icon=":material/verified_user:"),
            ],
        }
    )
    with st.sidebar:
        org = repo.get_organization(user.id)
        st.markdown(f"**{ui.md_safe(org['name']) if org and org['name'] else 'Your organization'}**")
        st.caption(user.email)
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            session.end("You have been logged out.")
            st.rerun()
        st.caption("In active development · not yet for confidential information")

try:
    page.run()
except Exception:  # Streamlit's stop/rerun signals are BaseException and pass through
    ref = uuid.uuid4().hex[:8]
    log.exception("Unhandled error on page %s (ref %s)", page.title, ref)
    st.error(f"Something went wrong on this page. Your data is safe. Reference: {ref}")
