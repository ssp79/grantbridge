"""Sample grant fixtures, the demo nonprofit profile, and the one-click demo loader."""

import json
from datetime import date

import pytest

from grantbridge import auth, demo, repo, ui, validation as v
from grantbridge.db import SAMPLE_GRANTS_FILE, SAMPLE_LABEL, connect, load_sample_grants, seed_sample_grants

PASSWORD = "correct horse battery staple"
REQUIRED_KEYS = {
    "id", "label", "title", "funder", "funder_type", "summary", "amount_min", "amount_max",
    "deadline", "focus_areas", "eligible_states", "eligibility", "questions",
}
FIXTURE_GRANTS = json.loads(SAMPLE_GRANTS_FILE.read_text(encoding="utf-8"))
DEMO = demo.demo_fixture()


# ---------------------------------------------------------------- grant fixtures

def test_between_8_and_12_grants_with_unique_ids_and_titles():
    assert 8 <= len(FIXTURE_GRANTS) <= 12
    assert len({g["id"] for g in FIXTURE_GRANTS}) == len(FIXTURE_GRANTS)
    assert len({g["title"] for g in FIXTURE_GRANTS}) == len(FIXTURE_GRANTS)


@pytest.mark.parametrize("grant", FIXTURE_GRANTS, ids=lambda g: g["id"])
def test_every_grant_is_labeled_sample_not_live(grant):
    assert grant["label"] == SAMPLE_LABEL == "SAMPLE / NOT LIVE"
    assert grant["id"].startswith("sample-")
    assert grant["funder"].startswith("Sample ")
    assert "source_url" not in grant  # a sample never claims a real source


@pytest.mark.parametrize("grant", FIXTURE_GRANTS, ids=lambda g: g["id"])
def test_every_grant_is_well_formed(grant):
    assert REQUIRED_KEYS <= grant.keys()
    assert 0 < grant["amount_min"] <= grant["amount_max"]
    if grant["deadline"] != "rolling":
        date.fromisoformat(grant["deadline"])
    assert grant["focus_areas"] and set(grant["focus_areas"]) <= set(v.FOCUS_AREAS)
    assert grant["eligible_states"] == ["ALL"] or set(grant["eligible_states"]) <= set(v.US_STATES)
    assert len(grant["eligibility"]) >= 3
    assert grant["questions"]
    for q in grant["questions"]:
        assert ui.word_limit(q), f"question has no (N words) limit: {q}"


def test_unlabeled_fixture_is_refused(tmp_path):
    bad = [dict(FIXTURE_GRANTS[0], label="LIVE")]
    path = tmp_path / "grants.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="SAMPLE / NOT LIVE"):
        load_sample_grants(path)


def test_catalog_in_database_matches_fixture_file():
    grants = repo.list_grants()
    assert {g["id"] for g in grants} == {g["id"] for g in FIXTURE_GRANTS}
    assert all(g["is_example"] and g["source_url"] == "" for g in grants)


def test_reseeding_removes_samples_no_longer_in_the_file(tmp_path):
    with connect() as conn:
        conn.execute(
            "INSERT INTO grants (id, title, funder, funder_type, summary, deadline, focus_areas, "
            "eligible_states, eligibility, questions, is_example) "
            "VALUES ('ex-old', 'Old', 'Old', 'x', 'x', 'rolling', '[]', '[]', '[]', '[]', 1)"
        )
        seed_sample_grants(conn)
    assert repo.get_grant("ex-old") is None


# ---------------------------------------------------------------- demo nonprofit

def test_demo_profile_is_clearly_labelled_sample_connecticut_youth_tutoring():
    """The demo organization must say on its face that it is a sample, wherever its name is shown."""
    profile = DEMO["profile"]
    assert "sample" in DEMO["_note"].lower()
    assert "sample" in profile["name"].lower()
    assert profile["state"] == "CT"
    assert {"Education", "Youth"} <= set(profile["focus_areas"])
    assert "tutor" in profile["programs"].lower()
    assert profile["ein"] == "" and profile["website"] == ""  # no real-looking identifiers


def test_demo_profile_passes_validation_and_fills_every_key_field():
    user = auth.sign_up("a@example.org", PASSWORD, "Placeholder")
    saved = repo.save_organization(user.id, DEMO["profile"])
    assert repo.missing_profile_fields(saved) == []
    assert saved["tax_status"] in v.TAX_STATUSES


def test_demo_references_only_existing_sample_grants():
    ids = {g["id"] for g in FIXTURE_GRANTS}
    assert set(DEMO["saved_grants"]) <= ids
    assert DEMO["application"]["grant_id"] in ids


def test_samples_give_the_demo_both_fits_and_misfits():
    """The eligibility demo needs passes and failures to be convincing."""
    profile = DEMO["profile"]
    open_to_ct = [g for g in FIXTURE_GRANTS if "ALL" in g["eligible_states"] or "CT" in g["eligible_states"]]
    closed_to_ct = [g for g in FIXTURE_GRANTS if g not in open_to_ct]
    ask = profile["requested_amount"]
    in_range = [g for g in FIXTURE_GRANTS if g["amount_min"] <= ask <= g["amount_max"]]
    assert open_to_ct and closed_to_ct
    assert in_range and len(in_range) < len(FIXTURE_GRANTS)


# ---------------------------------------------------------------- one-click loader

def test_load_demo_data_fills_profile_saves_grants_and_starts_application():
    user = auth.sign_up("a@example.org", PASSWORD, "My Org")
    app_id = demo.load_demo_data(user.id)
    org = repo.get_organization(user.id)
    assert org["name"] == DEMO["profile"]["name"]
    assert org["requested_amount"] == 25000
    assert repo.saved_grant_ids(user.id) == set(DEMO["saved_grants"])
    app = repo.get_application(user.id, app_id)
    assert app["grant_id"] == DEMO["application"]["grant_id"]
    assert app["due_date"] == repo.get_grant(app["grant_id"])["deadline"]
    assert len(repo.list_sections(user.id, app_id)) == len(repo.get_grant(app["grant_id"])["questions"])


def test_load_demo_data_twice_does_not_duplicate():
    user = auth.sign_up("a@example.org", PASSWORD, "My Org")
    first = demo.load_demo_data(user.id)
    assert demo.load_demo_data(user.id) == first
    assert len(repo.list_applications(user.id)) == 1


def test_load_demo_data_only_touches_the_current_user():
    alice = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    demo.load_demo_data(alice.id)
    assert repo.get_organization(bob.id)["name"] == "Bob Org"
    assert repo.list_applications(bob.id) == []
    assert repo.saved_grant_ids(bob.id) == set()


def test_old_databases_get_new_columns_and_tax_status_wording(fresh_db):
    import sqlite3

    from grantbridge.db import init_db

    user = auth.sign_up("a@example.org", PASSWORD, "Old Org")
    raw = sqlite3.connect(fresh_db)
    raw.execute("UPDATE organizations SET tax_status = '501(c)(3) public charity'")
    raw.execute("ALTER TABLE organizations DROP COLUMN track_record")
    raw.commit()
    raw.close()
    init_db()
    org = repo.get_organization(user.id)
    assert org["track_record"] == ""
    assert org["tax_status"] == "Yes, IRS-recognized 501(c)(3)"


def test_the_schema_fingerprint_changes_when_the_tables_do(monkeypatch):
    """Regression (2026-10-21): a server left running overnight never created the tables added during the day,
    because its one-time setup was cached for the whole process. The setup is now keyed on this fingerprint."""
    from grantbridge import db

    before = db.schema_version()
    assert before == db.schema_version() and len(before) == 12
    monkeypatch.setattr(db, "SCHEMA", db.SCHEMA + "\nCREATE TABLE IF NOT EXISTS added_later (id INTEGER);")
    assert db.schema_version() != before
    monkeypatch.undo()
    monkeypatch.setitem(db.ADDED_COLUMNS, "users", {**db.ADDED_COLUMNS["users"], "new_column": "TEXT"})
    assert db.schema_version() != before
