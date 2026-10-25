"""The Getting Started walkthrough: real progress, revisitable steps, and no leakage between accounts."""

import pytest

from grantbridge import auth, components as c
from grantbridge import demo, repo
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text

WALKTHROUGH = "app_pages/getting_started.py"


@pytest.fixture
def account():
    return auth.sign_up("alice@example.org", PASSWORD, "Alice Org")


def open_walkthrough():
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    return at.switch_page(WALKTHROUGH).run()


def test_every_step_is_listed_and_revisitable(account):
    at = open_walkthrough()
    assert not at.exception
    body = page_text(at)
    for n, (_, title, *_rest) in enumerate(c.WALKTHROUGH, 1):
        assert f"{n}. {title}" in body
    # a finished account can still open every step: no step is hidden or locked
    labels = [b.label for b in at.button]
    for _, _, _, action, _ in c.WALKTHROUGH:
        assert action in labels


def test_progress_is_read_from_the_account_not_invented(account):
    at = open_walkthrough()
    assert [s["state"] for s in c.walkthrough_progress(account.id)] == ["todo"] * 6
    assert "No grants saved yet" in page_text(at)  # the evidence line under the step

    repo.save_grant(account.id, "sample-01")
    at = open_walkthrough()
    rows = {s["key"]: s for s in c.walkthrough_progress(account.id)}
    assert rows["discover"]["state"] == "done"
    assert "1 grant(s) saved" in page_text(at)


def test_opening_the_walkthrough_changes_nothing(account):
    repo.save_organization(account.id, {"name": "Alice Org", "mission": "Ours"})
    before = repo.get_organization(account.id)
    open_walkthrough()
    assert repo.get_organization(account.id)["mission"] == before["mission"]
    assert repo.list_applications(account.id) == [] and repo.saved_grant_ids(account.id) == set()


def test_resume_points_at_the_first_unfinished_step(account):
    at = open_walkthrough()
    assert "Resume: set up your nonprofit profile" in "\n".join(b.label for b in at.button)
    demo.load_demo_data(account.id)  # profile and saved grants now done; evaluating is next
    at = open_walkthrough()
    assert "Resume: evaluate whether to pursue a grant" in "\n".join(b.label for b in at.button)


def test_the_walkthrough_offers_the_demo_and_can_remove_it(account):
    at = open_walkthrough()
    at.button(key="walk_demo_load").click().run()
    assert demo.demo_loaded(account.id)
    at = open_walkthrough()
    assert "The sample data is loaded" in page_text(at)
    at.button(key="walk_demo_remove").click().run()
    assert not demo.demo_loaded(account.id)


def test_progress_is_per_account(account):
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    demo.load_demo_data(account.id)
    alice_done = [s for s in c.walkthrough_progress(account.id) if s["state"] == "done"]
    bob_done = [s for s in c.walkthrough_progress(bob.id) if s["state"] == "done"]
    assert alice_done and not bob_done, "one account's progress must not show in another"


def test_a_step_reports_why_it_is_marked_done(account):
    demo.load_demo_data(account.id)
    rows = {s["key"]: s for s in c.walkthrough_progress(account.id)}
    assert rows["discover"]["state"] == "done" and "2 grant(s) saved" in rows["discover"]["evidence"]
    assert rows["timeline"]["state"] == "todo" and "No workback plan" in rows["timeline"]["evidence"]
