"""The guided setup flow, and keeping the sample demo data separable from a user's own work."""

import pytest

from grantbridge import auth, demo, repo
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text

SETUP = "app_pages/setup.py"
DASHBOARD = "app_pages/dashboard.py"


@pytest.fixture
def account():
    return auth.sign_up("alice@example.org", PASSWORD, "Alice Org")


def open_setup(account):
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    return at.switch_page(SETUP).run()


# ---------------------------------------------------------------- the flow itself

def test_setup_saves_each_step_and_can_be_resumed(account):
    at = open_setup(account)
    assert not at.exception and "Step 1 of 3" in page_text(at)

    at.text_input[0].set_value("Harborlight Literacy")
    at.selectbox[0].set_value("CT")
    at.selectbox[1].set_value("Yes, IRS-recognized 501(c)(3)")
    at.button(key="FormSubmitter:setup_0-Save and continue").click().run()
    saved = repo.get_organization(account.id)
    assert saved["name"] == "Harborlight Literacy" and saved["state"] == "CT"
    assert "Step 2 of 3" in page_text(at)  # the flow moved on by itself

    at.text_area[0].set_value("We teach adults to read in New Haven.")
    at.button(key="FormSubmitter:setup_1-Save and continue").click().run()
    assert repo.get_organization(account.id)["mission"] == "We teach adults to read in New Haven."
    assert "Step 3 of 3" in page_text(at)

    # leaving and coming back keeps what was saved; the step counter starts again, the answers do not
    back = log_in(fresh_app(), "alice@example.org", PASSWORD).switch_page(SETUP).run()
    assert back.text_input[0].value == "Harborlight Literacy"


def test_setup_is_skippable_and_never_blocks_the_app(account):
    at = open_setup(account)
    at.button(key="setup_skip_all").click().run()
    assert not at.exception
    org = repo.get_organization(account.id)
    assert org["mission"] in (None, "")  # nothing was written
    # the dashboard offers the way back in rather than forcing it
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    assert "Set up your organization" in "\n".join(b.label for b in at.button)


def test_a_step_can_be_skipped_without_losing_the_others(account):
    at = open_setup(account)
    at.button(key="setup_skip_step").click().run()
    assert "Step 2 of 3" in page_text(at)
    at.text_area[0].set_value("Reading tutors for adults.")
    at.button(key="FormSubmitter:setup_1-Save and continue").click().run()
    org = repo.get_organization(account.id)
    assert org["mission"] == "Reading tutors for adults." and org["name"] == "Alice Org"  # sign-up name kept


def test_setup_reports_what_is_still_missing_instead_of_guessing(account):
    at = open_setup(account)
    for _ in range(3):
        at.button(key="setup_skip_step").click().run()
    body = page_text(at)
    assert "That is everything GrantBridge needs to start" in body
    assert "Still blank" in body and "Mission" in body


def test_an_invalid_entry_keeps_the_user_on_the_step(account):
    at = open_setup(account)
    at.text_input[0].set_value("   ")  # a blank organization name is rejected by validation
    at.button(key="FormSubmitter:setup_0-Save and continue").click().run()
    assert not at.exception
    assert "Step 1 of 3" in page_text(at)  # not advanced past the error
    assert repo.get_organization(account.id)["name"] == "Alice Org"  # nothing was overwritten


# ---------------------------------------------------------------- sample data cannot cost a user their own work

def test_demo_data_is_recorded_and_can_be_removed_exactly(account):
    repo.save_organization(account.id, {"name": "Alice Org", "mission": "Our own mission", "state": "NY"})
    repo.save_grant(account.id, "sample-03")  # something the user saved themselves
    own_app = repo.create_application_from_grant(account.id, "sample-03")

    demo.load_demo_data(account.id)
    assert demo.demo_loaded(account.id)
    assert repo.get_organization(account.id)["mission"] != "Our own mission"  # the demo took over

    removed = demo.remove_demo_data(account.id)
    assert removed["profile_restored"]
    org = repo.get_organization(account.id)
    assert org["mission"] == "Our own mission" and org["state"] == "NY"  # put back exactly
    assert repo.get_application(account.id, own_app) is not None  # the user's own work is untouched
    assert "sample-03" in repo.saved_grant_ids(account.id)
    assert not demo.demo_loaded(account.id)


def test_removing_demo_data_leaves_work_done_after_it_was_loaded(account):
    demo.load_demo_data(account.id)
    mine = repo.create_application_from_grant(account.id, "sample-07")
    repo.save_grant(account.id, "sample-07")
    demo.remove_demo_data(account.id)
    assert repo.get_application(account.id, mine) is not None
    assert "sample-07" in repo.saved_grant_ids(account.id)


def test_the_page_warns_before_the_demo_replaces_real_work(account):
    repo.save_organization(account.id, {"name": "Alice Org", "mission": "Our own mission"})
    assert demo.would_replace(account.id)  # something to lose
    at = open_setup(account)
    assert "This would replace" in page_text(at)
    at.button(key="setup_demo_load").click().run()
    at = log_in(fresh_app(), "alice@example.org", PASSWORD).switch_page(SETUP).run()
    assert "Remove the sample data" in "\n".join(b.label for b in at.button)


def test_a_fresh_account_is_not_warned(account):
    assert demo.would_replace(account.id) == []  # only the sign-up name is set
    assert "This would replace" not in page_text(open_setup(account))


def test_demo_data_stays_inside_one_account(account):
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    demo.load_demo_data(account.id)
    assert demo.demo_loaded(account.id) and not demo.demo_loaded(bob.id)
    assert repo.list_applications(bob.id) == [] and repo.saved_grant_ids(bob.id) == set()
    demo.remove_demo_data(bob.id)  # a no-op for Bob
    assert demo.demo_loaded(account.id), "removing Bob's demo data must not touch Alice's"
