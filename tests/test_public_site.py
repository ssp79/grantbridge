"""The public website: five separate pages, one top navigation bar, and nothing private reachable from any of them.

Replaces the old single-page test file. Each public page is opened on its own, so a test fails if content drifts
back onto Home, and the navigation checks follow the journey a logged-out visitor actually takes.
"""

import re
from datetime import date
from pathlib import Path

import pytest

from grantbridge import auth, award_feasibility, demo, public, pursuit, repo, timeline
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text

ROOT = Path(__file__).resolve().parents[1]
HOME = "app_pages/about.py"
ABOUT_US = "app_pages/about_us.py"
TRY_FEATURES = "app_pages/try_features.py"
HOW_IT_WORKS = "app_pages/how_it_works.py"
TRUST = "app_pages/trust.py"
SIGN_IN = "app_pages/sign_in.py"
PUBLIC_FILES = {Path(p).name for p in public.PUBLIC_PAGES}
PRIVATE_PAGES = sorted(p.name for p in (ROOT / "app_pages").glob("*.py") if p.name not in PUBLIC_FILES)
HEADLINE = "Less time chasing funding. More time changing lives."


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    monkeypatch.setattr(timeline, "current_date", lambda: date(2026, 10, 21))


def text(at) -> str:
    return page_text(at) + "\n" + "\n".join(b.label for b in at.button)


def open_public(path: str):
    at = fresh_app()
    if path != HOME:
        at.switch_page(path).run()
    return at


# ---------------------------------------------------------------- every public page stands on its own

@pytest.mark.parametrize("path, title", [
    (HOME, HEADLINE),
    (ABOUT_US, "Helping small nonprofits compete for funding"),
    (TRY_FEATURES, "See it decide: a working example you can change"),
    (HOW_IT_WORKS, "From a blank profile to a submitted application"),
    (TRUST, "Code decides. The AI explains. You check the funder."),
])
def test_each_public_page_opens_logged_out_with_its_own_title(path, title):
    at = open_public(path)
    assert not at.exception
    assert at.title[0].value == title


@pytest.mark.parametrize("path", [HOME, ABOUT_US, TRY_FEATURES, HOW_IT_WORKS, TRUST])
def test_every_public_page_carries_the_same_footer(path):
    """One footer on every page, linking the whole site together."""
    at = open_public(path)
    body = text(at)
    assert "Grant strategy for small nonprofits." in body
    assert public.FOOTER_NOTE in body


# ---------------------------------------------------------------- Home is short, and keeps nothing it moved away

def test_home_keeps_the_hero_the_positioning_and_the_explore_cards():
    at = open_public(HOME)
    body = text(at)
    assert ("Meet your AI-powered grant strategy partner. GrantBridge helps resource-constrained nonprofits "
            "discover funding opportunities, evaluate which grants are worth pursuing, develop stronger "
            "proposals, and make the most of limited staff time.") in body
    assert ("### Most grant-writing tools help you apply. GrantBridge helps you decide what is worth applying "
            "for.") in body
    assert "Discover what GrantBridge can do for you" in body
    links = {str(e.proto.label): e.proto.page for e in at.get("page_link")}
    for title, _blurb, target in public.EXPLORE:
        assert title in links, f"no card for {title}"   # one card per other public page
    assert "Open" not in [b.label for b in at.button]   # the card itself is the link


def test_home_no_longer_holds_the_other_pages_content():
    """The whole point of the refactor: Home must not be the site in one scroll."""
    body = text(open_public(HOME))
    moved = {
        "the mission statement": "Great ideas shouldn't go unfunded",
        "the interactive demo": "SAMPLE DATA",
        "the nine-feature grid": "Everything a small grants team needs",
        "the six-step guide": "How to use GrantBridge",
        "the responsible-AI detail": "Passwords are stored only as salted Argon2id hashes",
    }
    still_here = [name for name, needle in moved.items() if needle in body]
    assert not still_here, f"still on Home: {still_here}"


# ---------------------------------------------------------------- each moved section landed on its own page

def test_about_us_holds_the_mission_and_says_what_is_unfinished():
    body = text(open_public(ABOUT_US))
    assert "Great ideas shouldn't go unfunded because an organization lacks a dedicated grant-writing team." in body
    assert "The problem" in body and "Who it is for" in body
    assert "no independent security audit" in body and "confidential information" in body
    for word in (" first ", "the only", "the best", "most accurate"):
        assert word not in body.lower()


def test_how_it_works_holds_all_six_steps_as_a_numbered_timeline():
    at = open_public(HOW_IT_WORKS)
    body = text(at)
    from app_pages import how_it_works  # noqa: F401  (imported for its STEPS mapping only)
    from grantbridge import components as c
    assert len(c.WALKTHROUGH) == 6
    for n, (key, *_rest) in enumerate(c.WALKTHROUGH, 1):
        assert f"{n:02d}" in body                      # 01 … 06, not a grey "Step 1" badge
        assert f"Step {n}" not in body
    assert "Start with your organization" in body and "Stay on track to the deadline" in body


def test_how_it_works_has_one_registration_call_to_action_at_the_end():
    at = open_public(HOW_IT_WORKS)
    labels = [b.label for b in at.button]
    assert labels.count("Get started") == 1
    assert "Create an account" not in labels          # none inside the individual steps
    assert "Explore the interactive demo" in labels


def test_every_expander_on_how_it_works_is_closed_and_labelled_for_its_step():
    at = open_public(HOW_IT_WORKS)
    labels = [e.label for e in at.expander]
    assert len(labels) == 6 and "More detail" not in labels
    assert "How to build your nonprofit profile" in labels and "How to search and save grants" in labels


def test_trust_page_states_both_the_safeguards_and_the_limits():
    body = text(open_public(TRUST))
    assert "Passwords are stored only as salted Argon2id hashes" in body
    assert "do not upload confidential documents" in body.lower()  # the upload limit is stated, not hidden
    assert "What we do not claim" in body and "no independent security audit" in body
    assert "No measured time savings" in body


# ---------------------------------------------------------------- Try Features is the live demonstration

def test_try_features_runs_the_real_rules_on_sample_data():
    at = open_public(TRY_FEATURES)
    body = text(at)
    data = pursuit.example(date(2026, 10, 21))
    assert data["outcome"] == "verify" and data["after_confirming"]["outcome"] == "strong"
    assert ":orange-badge[:material/science: SAMPLE DATA]" in body
    assert "Harbor Lantern Tutoring Collective" in body and "sample organization" in body
    assert pursuit.OUTCOMES["verify"][0] in body and "gives: Strong candidate" in body


def test_changing_a_demo_input_changes_the_answer():
    at = open_public(TRY_FEATURES)
    base = award_feasibility.demo()
    assert base["verdict"]["level"] == "burden"
    shown = {m.label: m.value for m in at.metric}
    assert shown["Match to fund"] == award_feasibility.usd(base["result"]["match_needed"]) == "$55,000"

    at.slider(key="about_demo_match").set_value(0).run()
    no_match = award_feasibility.demo({"payment_delay_days": 90, "match_percent": 0, "payment_type": "reimbursement"})
    shown = {m.label: m.value for m in at.metric}
    assert shown["Match to fund"] == "$0"
    assert shown["Cash tied up at the worst point"] == award_feasibility.usd(no_match["result"]["peak_need"])
    assert no_match["result"]["peak_need"] < base["result"]["peak_need"]


def test_the_toggle_on_the_pursue_demo_changes_the_outcome():
    at = open_public(TRY_FEATURES)
    assert pursuit.OUTCOMES["verify"][0] in text(at)
    at.toggle(key="about_demo_confirm").set_value(True).run()
    assert pursuit.OUTCOMES["strong"][0] in text(at)


def test_the_grant_picker_changes_the_outcome():
    """The same rules, a different grant, a different answer: the point of letting visitors choose."""
    at = open_public(TRY_FEATURES)
    assert pursuit.OUTCOMES["verify"][0] in text(at)          # sample-05, the default
    at.get("button_group")[0].set_value("sample-07").run()    # a grant that fails a required rule
    assert pursuit.OUTCOMES["do_not_pursue"][0] in text(at)
    assert pursuit.example(date(2026, 10, 21), "sample-07")["outcome"] == "do_not_pursue"


def test_the_workback_demo_tightens_as_the_deadline_nears():
    at = open_public(TRY_FEATURES)
    assert "There is time to do this properly" in text(at)    # 60 days: the default
    at.slider(key="about_demo_days").set_value(10).run()
    body = text(at)
    assert "Not enough time for this plan" in body
    assert "The seven steps normally need" in body


def test_dollar_amounts_render_as_money_not_math():
    """An unescaped pair of dollar signs makes Streamlit set the text as a LaTeX formula."""
    for path in (HOME, ABOUT_US, TRY_FEATURES, HOW_IT_WORKS, TRUST):
        at = open_public(path)
        for el in list(at.markdown) + list(at.caption):
            assert not re.search(r"(?<!\\)\$", el.value), (path, el.value)


# ---------------------------------------------------------------- navigation

def test_a_visitor_can_reach_every_public_page_and_back_to_home():
    at = fresh_app()
    for path, title in ((ABOUT_US, "Helping small nonprofits compete for funding"),
                        (TRY_FEATURES, "See it decide: a working example you can change"),
                        (HOW_IT_WORKS, "From a blank profile to a submitted application"),
                        (TRUST, "Code decides. The AI explains. You check the funder."),
                        (HOME, HEADLINE)):
        at.switch_page(path).run()
        assert not at.exception and at.title[0].value == title


@pytest.mark.parametrize("page, button, target", [
    (HOME, "about_start_hero", "See it decide: a working example you can change"),   # Try GrantBridge
    (HOME, "about_create_hero", "From a blank profile to a submitted application"),  # How it works
    (HOME, "home_go_trust_line", "Code decides. The AI explains. You check the funder."),
])
def test_home_buttons_open_other_pages_not_sections_of_home(page, button, target):
    at = open_public(page)
    at.button(key=button).click().run()
    assert not at.exception and at.title[0].value == target


@pytest.mark.parametrize("button, tab", [("about_signin_hero", "Log in"),
                                         ("about_start_closing", "Create account"),
                                         ("about_signin_closing", "Log in")])
def test_sign_in_and_get_started_open_the_right_tab(button, tab):
    at = open_public(HOME)
    at.button(key=button).click().run()
    assert not at.exception
    assert at.title[0].value == "GrantBridge"  # the Sign in page
    assert at.session_state["auth_tab"] == tab
    assert [t.label for t in at.tabs] == ["Log in", "Create account"]


def test_signing_in_from_the_public_site_opens_the_dashboard():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    assert not at.exception and at.title[0].value == "Your funding workspace"


def test_signed_in_users_can_still_reach_the_public_pages():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page(TRUST).run()
    assert not at.exception and at.title[0].value == "Code decides. The AI explains. You check the funder."


# ---------------------------------------------------------------- private stays private

@pytest.mark.parametrize("page", PRIVATE_PAGES)
def test_no_private_page_is_even_registered_for_visitors(page):
    """Signed out, the router knows only the public pages: a private page cannot be opened at all."""
    owner = auth.sign_up("alice@example.org", PASSWORD, "Alice Secret Org")
    demo.load_demo_data(owner.id)
    at = fresh_app()
    with pytest.raises(ValueError, match="Known pages:"):
        at.switch_page(f"app_pages/{page}")
    assert "Alice Secret Org" not in text(at) and "alice@example.org" not in text(at)


def test_every_private_page_checks_the_session_itself():
    for page in PRIVATE_PAGES:
        source = (ROOT / "app_pages" / page).read_text(encoding="utf-8")
        assert "session.require_user()" in source, page


@pytest.mark.parametrize("path", [HOME, ABOUT_US, TRY_FEATURES, HOW_IT_WORKS, TRUST])
def test_no_public_page_reads_account_data(path):
    source = (ROOT / Path(path)).read_text(encoding="utf-8")
    assert "repo." not in source and "session.require_user()" not in source
    secret = auth.sign_up("alice@example.org", PASSWORD, "Alice Secret Org")
    demo.load_demo_data(secret.id)
    repo.save_organization(secret.id, {"name": "Alice Secret Org", "mission": "PRIVATE-MISSION-TEXT"})
    body = text(open_public(path))
    assert "Alice Secret Org" not in body and "PRIVATE-MISSION-TEXT" not in body


# ---------------------------------------------------------------- the licensed photograph and the product still

def test_the_photo_is_a_local_optimized_image_with_alt_text_and_a_license_record():
    at = open_public(HOME)
    images = [img for el in at.get("image") for img in el.proto.imgs]
    assert len(images) == 1  # the hero photograph; the interface previews live on How It Works
    assert "://" not in images[0].url and "community team" in images[0].alt
    for path in ("photos/community-planning-1200.webp", "previews/site-find.webp", "previews/site-pursue.webp",
                 "previews/site-portfolio.webp"):
        assert (ROOT / "assets" / path).stat().st_size < 200_000, path
    record = (ROOT / "assets" / "photos" / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "https://unsplash.com/license" in record and "Sweet Life" in record and "Not allowed" in record
    assert "Sweet Life on Unsplash" in text(at) and "not affiliated with GrantBridge" in text(at)
