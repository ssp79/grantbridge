"""Cross-account access is denied: user B cannot read, change, or delete user A's data."""

import pytest

from grantbridge import auth, repo

PASSWORD = "correct horse battery staple"


@pytest.fixture
def alice_and_bob():
    alice = auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Arts")
    repo.save_organization(alice.id, {"name": "Alice Pantry", "mission": "Alice's secret mission"})
    app_id = repo.create_application_from_grant(alice.id, "sample-01")
    section = repo.list_sections(alice.id, app_id)[0]
    repo.save_section_answer(alice.id, section.id, "Alice's private answer")
    repo.add_message(alice.id, "user", "Alice's private question")
    repo.save_grant(alice.id, "sample-02")
    return alice, bob, app_id, section.id


def test_profile_is_private(alice_and_bob):
    alice, bob, *_ = alice_and_bob
    assert repo.get_organization(bob.id)["mission"] == ""
    repo.save_organization(bob.id, {"name": "Bob Arts", "mission": "Bob's mission"})
    assert repo.get_organization(alice.id)["mission"] == "Alice's secret mission"


def test_cannot_list_or_read_another_users_application(alice_and_bob):
    _, bob, app_id, _ = alice_and_bob
    assert repo.list_applications(bob.id) == []
    assert repo.get_application(bob.id, app_id) is None
    assert repo.list_sections(bob.id, app_id) == []
    assert repo.application_for_grant(bob.id, "sample-01") is None


def test_cannot_update_another_users_application(alice_and_bob):
    alice, bob, app_id, _ = alice_and_bob
    with pytest.raises(repo.NotFound):
        repo.update_application(bob.id, app_id, {"status": "Declined"})
    assert repo.get_application(alice.id, app_id)["status"] == "Researching"


def test_cannot_delete_another_users_application(alice_and_bob):
    alice, bob, app_id, _ = alice_and_bob
    with pytest.raises(repo.NotFound):
        repo.delete_application(bob.id, app_id)
    assert repo.get_application(alice.id, app_id) is not None


def test_cannot_edit_add_or_delete_another_users_sections(alice_and_bob):
    alice, bob, app_id, section_id = alice_and_bob
    with pytest.raises(repo.NotFound):
        repo.save_section_answer(bob.id, section_id, "overwritten by Bob")
    with pytest.raises(repo.NotFound):
        repo.add_section(bob.id, app_id, "Bob's injected question")
    with pytest.raises(repo.NotFound):
        repo.delete_section(bob.id, section_id)
    sections = repo.list_sections(alice.id, app_id)
    assert sections[0].answer == "Alice's private answer"
    assert all("Bob" not in s.question for s in sections)


def test_advisor_history_is_private(alice_and_bob):
    alice, bob, *_ = alice_and_bob
    assert repo.list_messages(bob.id) == []
    repo.clear_messages(bob.id)
    assert len(repo.list_messages(alice.id)) == 1


def test_saved_grants_are_private(alice_and_bob):
    alice, bob, *_ = alice_and_bob
    assert repo.saved_grant_ids(bob.id) == set()
    repo.unsave_grant(bob.id, "sample-02")
    assert repo.saved_grant_ids(alice.id) == {"sample-02"}


def test_same_grant_gives_each_user_a_separate_application(alice_and_bob):
    alice, bob, app_id, _ = alice_and_bob
    bob_app = repo.create_application_from_grant(bob.id, "sample-01")
    assert bob_app != app_id
    assert repo.list_sections(bob.id, bob_app)[0].answer == ""
