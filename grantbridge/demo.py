"""One-click demo data: a sample youth-tutoring nonprofit.

Used by the setup flow, the "Load demo data" button on the Organization Profile page, and
scripts/create_demo_account.py. Loading is idempotent: running it again resets the profile to the demo values
without duplicating saved grants or applications.

The sample data is kept separable from a user's own work. `load_demo_data` records what it created and the
profile it replaced (`repo.save_demo_state`), and `remove_demo_data` takes exactly that back out, so exploring the
demo can never cost someone work they had already entered. `would_replace` says what a load would overwrite, so a
page can ask first.
"""

from __future__ import annotations

import json

from grantbridge import repo
from grantbridge.db import FIXTURES_DIR

DEMO_FILE = FIXTURES_DIR / "demo_profile.json"


def demo_fixture() -> dict:
    return json.loads(DEMO_FILE.read_text(encoding="utf-8"))


def would_replace(user_id: int) -> list[str]:
    """What loading the demo data would overwrite or add to, in words. Empty when the account is still untouched."""
    org = repo.get_organization(user_id) or {}
    # "name" is set for every account at sign-up, so it is not work the user would be surprised to lose.
    filled = [label for key, label in repo.KEY_PROFILE_FIELDS.items()
              if key != "name" and org.get(key) not in (None, "", [])]
    saved = [g for g in repo.list_saved_grants(user_id) if not g["is_example"]]
    apps = repo.list_applications(user_id)
    notes = []
    if filled:
        notes.append(f"your profile ({len(filled)} field(s) filled in, including {filled[0].lower()})")
    if saved:
        notes.append(f"{len(saved)} live grant(s) you saved")
    if apps:
        notes.append(f"{len(apps)} application(s)")
    return notes


def load_demo_data(user_id: int) -> int:
    """Fill this user's profile with the demo nonprofit and start one application.

    Only touches rows owned by `user_id`. Records what it created, and the profile as it was, so
    `remove_demo_data` can undo it exactly. Returns the demo application's id.
    """
    fixture = demo_fixture()
    before = repo.get_demo_state(user_id)
    profile_before = before.get("profile_before") if before else repo.get_organization(user_id)
    repo.save_organization(user_id, fixture["profile"])

    already_saved = {g["id"] for g in repo.list_saved_grants(user_id)}
    added_grants = []
    for grant_id in fixture["saved_grants"]:
        repo.save_grant(user_id, grant_id)
        if grant_id not in already_saved:
            added_grants.append(grant_id)

    app = fixture["application"]
    app_ids = {a["id"] for a in repo.list_applications(user_id)}
    app_id = repo.create_application_from_grant(user_id, app["grant_id"])
    current = repo.get_application(user_id, app_id)
    repo.update_application(user_id, app_id, {
        "status": app["status"],
        "due_date": current["due_date"],
        "amount_requested": app["amount_requested"],
        "notes": app["notes"],
    })
    state = {"profile_before": _plain(profile_before), "application_id": app_id if app_id not in app_ids else None,
             "grant_ids": sorted(set(before.get("grant_ids", [])) | set(added_grants)),
             "application_ids": sorted(set(before.get("application_ids", []))
                                       | ({app_id} if app_id not in app_ids else set()))}
    repo.save_demo_state(user_id, state)
    return app_id


def demo_loaded(user_id: int) -> bool:
    return bool(repo.get_demo_state(user_id))


def remove_demo_data(user_id: int) -> dict:
    """Take the sample data back out: the grants and applications it added, and the profile it replaced.

    Anything the user saved or wrote themselves after loading it is left alone, because only the rows recorded at
    load time are removed. Returns what was removed, in counts.
    """
    state = repo.get_demo_state(user_id)
    if not state:
        return {"grants": 0, "applications": 0, "profile_restored": False}
    for app_id in state.get("application_ids", []):
        try:
            repo.delete_application(user_id, app_id)
        except repo.NotFound:  # the user deleted it themselves already
            pass
    for grant_id in state.get("grant_ids", []):
        repo.unsave_grant(user_id, grant_id)
    before = state.get("profile_before") or {}
    if before.get("name"):  # the profile always has a name from sign-up; without one there is nothing safe to restore
        repo.save_organization(user_id, {key: before.get(key) for key in repo.PROFILE_FIELDS})
    repo.clear_demo_state(user_id)
    return {"grants": len(state.get("grant_ids", [])), "applications": len(state.get("application_ids", [])),
            "profile_restored": bool(before)}


def _plain(org: dict | None) -> dict | None:
    """The profile as plain JSON-safe values, or None when there was no profile to restore."""
    if not org:
        return None
    return {key: org.get(key) for key in repo.PROFILE_FIELDS if key in org}
