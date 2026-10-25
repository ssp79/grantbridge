"""Data access for everything a user owns.

Ownership rule: every function that touches user data takes `user_id` as its
first argument and filters on it in SQL. Pages pass the id from the logged-in
session (see session.py), never from a URL or form field. A row owned by someone
else behaves exactly like a missing row: reads return None, writes raise NotFound.

The grant catalog is shared, read-only reference data and has no owner.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from grantbridge import validation as v
from grantbridge.db import connect, now_iso

MAX_ANSWER_CHARS = 20_000
MAX_MESSAGE_CHARS = 4_000

# Storage caps: one account cannot grow the database without bound.
MAX_APPLICATIONS_PER_USER = 200
MAX_SECTIONS_PER_APPLICATION = 60
MAX_REQUIREMENTS_PER_APPLICATION = 100
OUTLINE_STATUSES = ("not started", "drafting", "ready")
COMPONENT_STATES = ("not started", "in hand", "not applicable")
MAX_FACTS_PER_SECTION = 50
MAX_MESSAGES_PER_USER = 500  # oldest advisor messages are pruned beyond this
MAX_DRAFTS_PER_SECTION = 10  # oldest drafts are pruned beyond this


def _check_application_cap(conn: sqlite3.Connection, user_id: int) -> None:
    count = conn.execute("SELECT COUNT(*) FROM applications WHERE user_id = ?", (user_id,)).fetchone()[0]
    if count >= MAX_APPLICATIONS_PER_USER:
        raise v.ValidationError(f"You have reached the limit of {MAX_APPLICATIONS_PER_USER} applications. "
                                "Delete old ones to start new ones.")


class NotFound(LookupError):
    """The record does not exist or is not owned by this user."""


# ---------------------------------------------------------------- organization

# Fields an eligibility check or draft needs. Annual budget and the rest are optional.
# Every column save_organization writes, in its order. Used to copy a profile verbatim (see demo.remove_demo_data).
PROFILE_FIELDS = ("name", "ein", "state", "city", "website", "mission", "programs", "population_served",
                  "tax_status", "requested_amount", "funding_purpose", "track_record", "annual_budget",
                  "staff_size", "founded_year", "focus_areas")

KEY_PROFILE_FIELDS = {
    "name": "Organization name",
    "mission": "Mission",
    "state": "State",
    "tax_status": "501(c)(3) status",
    "population_served": "Populations served",
    "programs": "Programs",
    "requested_amount": "Requested funding",
    "track_record": "Track record and outcomes",
}


def missing_profile_fields(org: dict | None) -> list[str]:
    """Labels of key fields that are still blank."""
    org = org or {}
    return [label for key, label in KEY_PROFILE_FIELDS.items() if org.get(key) in (None, "", [])]


def get_organization(user_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM organizations WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    org = dict(row)
    org["focus_areas"] = json.loads(org["focus_areas"])
    return org


def profile_facts(org: dict | None) -> dict:
    """The profile as facts for AI prompts: self-reported, with None for anything not provided."""
    org = org or {}

    def known(key):
        value = org.get(key)
        return value if value not in (None, "", []) else None

    return {
        "name": known("name"),
        "state": known("state"),
        "city": known("city"),
        "501c3_status_self_reported": known("tax_status"),
        "mission": known("mission"),
        "populations_served": known("population_served"),
        "programs": known("programs"),
        "focus_areas": org.get("focus_areas") or [],
        "requested_funding_usd": known("requested_amount"),
        "funding_purpose": known("funding_purpose"),
        "track_record_and_outcomes": known("track_record"),
        "annual_budget_usd": known("annual_budget"),
        "staff_fte": known("staff_size"),
        "year_founded": known("founded_year"),
    }


def save_organization(user_id: int, data: dict) -> dict:
    clean = {
        "name": v.text(data.get("name", ""), "Organization name", 200, required=True),
        "ein": v.ein(data.get("ein", "")),
        "state": v.state(data.get("state", "")),
        "city": v.text(data.get("city", ""), "City", 100),
        "website": v.url(data.get("website", "")),
        "mission": v.text(data.get("mission", ""), "Mission", 1500),
        "programs": v.text(data.get("programs", ""), "Programs", 3000),
        "population_served": v.text(data.get("population_served", ""), "Populations served", 1500),
        "tax_status": v.choice(data.get("tax_status", ""), v.TAX_STATUSES, "501(c)(3) status"),
        "requested_amount": v.optional_int(
            data.get("requested_amount"), "Requested funding", 0, 100_000_000
        ),
        "funding_purpose": v.text(data.get("funding_purpose", ""), "What the funding is for", 1500),
        "track_record": v.text(data.get("track_record", ""), "Track record and outcomes", 3000),
        "annual_budget": v.optional_int(data.get("annual_budget"), "Annual budget", 0, 1_000_000_000),
        "staff_size": v.optional_int(data.get("staff_size"), "Staff size", 0, 100_000),
        "founded_year": v.optional_int(data.get("founded_year"), "Year founded", 1800, 2100),
        "focus_areas": json.dumps(v.focus_areas(data.get("focus_areas") or [])),
    }
    assignments = ", ".join(f"{k} = ?" for k in clean)
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE organizations SET {assignments}, version = version + 1, updated_at = ? WHERE user_id = ?",
            (*clean.values(), now_iso(), user_id),
        )
        if cur.rowcount == 0:
            raise NotFound("Organization profile not found.")
    return get_organization(user_id)


# ---------------------------------------------------------------- grant catalog (shared)

def _grant_from_row(row: sqlite3.Row) -> dict:
    g = dict(row)
    for key in ("focus_areas", "eligible_states", "eligibility", "questions"):
        g[key] = json.loads(g[key])
    g["is_example"] = bool(g["is_example"])
    return g


def list_grants() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM grants ORDER BY deadline, title").fetchall()
    return [_grant_from_row(r) for r in rows]


def list_sample_grants() -> list[dict]:
    """Only the offline SAMPLE / NOT LIVE fixtures, never saved live snapshots."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM grants WHERE is_example = 1 ORDER BY deadline, title").fetchall()
    return [_grant_from_row(r) for r in rows]


def save_live_grant_snapshot(result) -> str:
    """Store a copy of a live Grants.gov result so an application can point at it.

    The snapshot keeps the source URL and retrieval time and is never shown as
    current: pages always say when it was retrieved and link to the source.
    `result` is a grant_search.GrantResult with source "grants.gov".
    """
    if not result.is_live or not str(result.id).isdigit():
        raise v.ValidationError("Only live Grants.gov results can be saved as snapshots.")
    grant_id = f"gg-{result.id}"
    deadline = result.close_date.isoformat() if result.close_date else "unknown"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO grants (id, title, funder, funder_type, summary, amount_min, amount_max, deadline,
                                focus_areas, eligible_states, eligibility, questions, source_url,
                                retrieved_at, is_example)
            VALUES (?, ?, ?, 'Federal agency (Grants.gov)', ?, ?, ?, ?, '[]', '[]', ?, '[]', ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, funder=excluded.funder, summary=excluded.summary,
                amount_min=excluded.amount_min, amount_max=excluded.amount_max, deadline=excluded.deadline,
                eligibility=excluded.eligibility, source_url=excluded.source_url,
                retrieved_at=excluded.retrieved_at
            """,
            (grant_id, result.title[:300], result.funder[:200], result.summary[:2000],
             result.amount_min, result.amount_max, deadline, json.dumps(list(result.eligibility)),
             result.source_url, result.retrieved_at.isoformat() if result.retrieved_at else ""),
        )
    return grant_id


def get_grant(grant_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone()
    return _grant_from_row(row) if row else None


# ---------------------------------------------------------------- saved grants

def saved_grant_ids(user_id: int) -> set[str]:
    with connect() as conn:
        rows = conn.execute("SELECT grant_id FROM saved_grants WHERE user_id = ?", (user_id,))
        return {r["grant_id"] for r in rows}


def list_saved_grants(user_id: int) -> list[dict]:
    """This user's saved grants (samples and dated Grants.gov snapshots), newest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT g.* FROM saved_grants s JOIN grants g ON g.id = s.grant_id
                WHERE s.user_id = ? ORDER BY s.created_at DESC, g.title""",
            (user_id,),
        ).fetchall()
    return [_grant_from_row(r) for r in rows]


def save_grant(user_id: int, grant_id: str) -> None:
    if get_grant(grant_id) is None:
        raise NotFound("Grant not found.")
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO saved_grants (user_id, grant_id, created_at) VALUES (?, ?, ?)",
            (user_id, grant_id, now_iso()),
        )


def unsave_grant(user_id: int, grant_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM saved_grants WHERE user_id = ? AND grant_id = ?", (user_id, grant_id)
        )


# ---------------------------------------------------------------- applications

@dataclass(frozen=True)
class Section:
    id: int
    position: int
    question: str
    answer: str


def list_applications(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_application(user_id: int, application_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ? AND user_id = ?", (application_id, user_id)
        ).fetchone()
    return dict(row) if row else None


def application_for_grant(user_id: int, grant_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE user_id = ? AND grant_id = ?", (user_id, grant_id)
        ).fetchone()
    return dict(row) if row else None


def _iso_or_blank(value: str) -> str:
    try:
        return v.optional_date(value)
    except v.ValidationError:
        return ""  # "rolling", "unknown", or anything else that is not a date


def create_application_from_grant(user_id: int, grant_id: str) -> int:
    """Start an application for a catalog grant, copying its questions as sections."""
    existing = application_for_grant(user_id, grant_id)
    if existing:
        return existing["id"]
    grant = get_grant(grant_id)
    if grant is None:
        raise NotFound("Grant not found.")
    created = now_iso()
    with connect() as conn:
        _check_application_cap(conn, user_id)
        cur = conn.execute(
            """INSERT INTO applications (user_id, grant_id, title, funder, status, due_date,
                                         created_at, updated_at)
               VALUES (?, ?, ?, ?, 'Researching', ?, ?, ?)""",
            (user_id, grant_id, grant["title"], grant["funder"],
             _iso_or_blank(grant["deadline"]), created, created),
        )
        app_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO application_sections (application_id, position, question, updated_at)
               VALUES (?, ?, ?, ?)""",
            [(app_id, i, q, created) for i, q in enumerate(grant["questions"])],
        )
    return app_id


def create_application(user_id: int, title: str, funder: str = "") -> int:
    clean_title = v.text(title, "Application title", 200, required=True)
    clean_funder = v.text(funder, "Funder", 200)
    created = now_iso()
    with connect() as conn:
        _check_application_cap(conn, user_id)
        cur = conn.execute(
            """INSERT INTO applications (user_id, title, funder, status, created_at, updated_at)
               VALUES (?, ?, ?, 'Researching', ?, ?)""",
            (user_id, clean_title, clean_funder, created, created),
        )
    return cur.lastrowid


def update_application(user_id: int, application_id: int, data: dict) -> None:
    clean = {
        "status": v.choice(data.get("status", ""), v.APPLICATION_STATUSES, "Status", allow_blank=False),
        "due_date": v.optional_date(data.get("due_date")),
        "amount_requested": v.optional_int(
            data.get("amount_requested"), "Amount requested", 0, 100_000_000
        ),
        "notes": v.text(data.get("notes", ""), "Notes", 5000),
    }
    assignments = ", ".join(f"{k} = ?" for k in clean)
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE applications SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
            (*clean.values(), now_iso(), application_id, user_id),
        )
        if cur.rowcount == 0:
            raise NotFound("Application not found.")


def delete_application(user_id: int, application_id: int) -> None:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM applications WHERE id = ? AND user_id = ?", (application_id, user_id)
        )
        if cur.rowcount == 0:
            raise NotFound("Application not found.")


def list_sections(user_id: int, application_id: int) -> list[Section]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT s.id, s.position, s.question, s.answer
                 FROM application_sections s
                 JOIN applications a ON a.id = s.application_id
                WHERE s.application_id = ? AND a.user_id = ?
                ORDER BY s.position""",
            (application_id, user_id),
        ).fetchall()
    return [Section(**dict(r)) for r in rows]


def add_section(user_id: int, application_id: int, question: str) -> int:
    clean = v.text(question, "Question", 1000, required=True)
    with connect() as conn:
        owner = conn.execute(
            "SELECT 1 FROM applications WHERE id = ? AND user_id = ?", (application_id, user_id)
        ).fetchone()
        if owner is None:
            raise NotFound("Application not found.")
        if conn.execute("SELECT COUNT(*) FROM application_sections WHERE application_id = ?",
                        (application_id,)).fetchone()[0] >= MAX_SECTIONS_PER_APPLICATION:
            raise v.ValidationError(f"An application can have at most {MAX_SECTIONS_PER_APPLICATION} questions.")
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) FROM application_sections WHERE application_id = ?",
            (application_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO application_sections (application_id, position, question, updated_at)
               VALUES (?, ?, ?, ?)""",
            (application_id, position, clean, now_iso()),
        )
    return cur.lastrowid


VERSION_SOURCES = ("user", "ai draft", "restored")
MAX_VERSIONS_PER_SECTION = 30


def save_section_answer(user_id: int, section_id: int, answer: str, source: str = "user") -> bool:
    """Save an answer and keep the text it replaced in the version history.

    Returns False (and records nothing) when the text did not change. Nothing a
    user saved is ever lost: the previous text stays in section_versions.
    """
    if source not in VERSION_SOURCES:
        raise v.ValidationError("Invalid version source.")
    clean = v.text(answer, "Answer", MAX_ANSWER_CHARS)
    with connect() as conn:
        row = _owned_section(conn, user_id, section_id)
        if row is None:
            raise NotFound("Section not found.")
        if row["answer"] == clean:
            return False
        created = now_iso()
        conn.execute("UPDATE application_sections SET answer = ?, updated_at = ? WHERE id = ?",
                     (clean, created, section_id))
        conn.execute("INSERT INTO section_versions (section_id, text, source, created_at) VALUES (?, ?, ?, ?)",
                     (section_id, clean, source, created))
        conn.execute(
            """DELETE FROM section_versions WHERE section_id = ? AND id NOT IN
                   (SELECT id FROM section_versions WHERE section_id = ? ORDER BY id DESC LIMIT ?)""",
            (section_id, section_id, MAX_VERSIONS_PER_SECTION),
        )
        conn.execute("UPDATE applications SET updated_at = ? WHERE id = ? AND user_id = ?",
                     (created, row["application_id"], user_id))
    return True


def delete_section(user_id: int, section_id: int) -> None:
    with connect() as conn:
        cur = conn.execute(
            """DELETE FROM application_sections
                WHERE id = ? AND application_id IN (SELECT id FROM applications WHERE user_id = ?)""",
            (section_id, user_id),
        )
        if cur.rowcount == 0:
            raise NotFound("Section not found.")


# ---------------------------------------------------------------- drafting workflow (owner-checked)

MAX_REQUIREMENT_CHARS = 500
MAX_FACT_CHARS = 2000


def _owned_section(conn: sqlite3.Connection, user_id: int, section_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT s.* FROM application_sections s JOIN applications a ON a.id = s.application_id
            WHERE s.id = ? AND a.user_id = ?""",
        (section_id, user_id),
    ).fetchone()


def _require_section(conn: sqlite3.Connection, user_id: int, section_id: int) -> sqlite3.Row:
    row = _owned_section(conn, user_id, section_id)
    if row is None:
        raise NotFound("Section not found.")
    return row


def _require_application(conn: sqlite3.Connection, user_id: int, application_id: int) -> None:
    if conn.execute("SELECT 1 FROM applications WHERE id = ? AND user_id = ?",
                    (application_id, user_id)).fetchone() is None:
        raise NotFound("Application not found.")


def get_section(user_id: int, section_id: int) -> dict | None:
    with connect() as conn:
        row = _owned_section(conn, user_id, section_id)
    return dict(row) if row else None


def add_sections(user_id: int, application_id: int, questions: list[str]) -> list[int]:
    return [add_section(user_id, application_id, q) for q in questions]


def list_requirements(user_id: int, application_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.id, r.position, r.text, r.created_at FROM application_requirements r
                 JOIN applications a ON a.id = r.application_id
                WHERE r.application_id = ? AND a.user_id = ? ORDER BY r.position""",
            (application_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


def add_requirements(user_id: int, application_id: int, texts: list[str]) -> int:
    clean = [v.text(t, "Requirement", MAX_REQUIREMENT_CHARS, required=True) for t in texts if (t or "").strip()]
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        existing = conn.execute("SELECT COUNT(*) FROM application_requirements WHERE application_id = ?",
                                (application_id,)).fetchone()[0]
        if existing + len(clean) > MAX_REQUIREMENTS_PER_APPLICATION:
            raise v.ValidationError(f"An application can have at most {MAX_REQUIREMENTS_PER_APPLICATION} "
                                    "requirements.")
        start = conn.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM application_requirements "
                             "WHERE application_id = ?", (application_id,)).fetchone()[0]
        conn.executemany(
            "INSERT INTO application_requirements (application_id, position, text, created_at) VALUES (?, ?, ?, ?)",
            [(application_id, start + i, t, now_iso()) for i, t in enumerate(clean)],
        )
    return len(clean)


def delete_requirement(user_id: int, requirement_id: int) -> None:
    with connect() as conn:
        cur = conn.execute(
            """DELETE FROM application_requirements WHERE id = ?
                 AND application_id IN (SELECT id FROM applications WHERE user_id = ?)""",
            (requirement_id, user_id),
        )
        if cur.rowcount == 0:
            raise NotFound("Requirement not found.")


def list_section_facts(user_id: int, section_id: int) -> list[dict]:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        rows = conn.execute("SELECT * FROM section_facts WHERE section_id = ? ORDER BY id", (section_id,)).fetchall()
    return [dict(r) for r in rows]


def add_section_fact(user_id: int, section_id: int, prompt: str, *, answer: str = "",
                     status: str = "pending", source: str = "user") -> int:
    if status not in ("pending", "answered", "skipped") or source not in ("ai", "mock", "user"):
        raise v.ValidationError("Invalid fact.")
    clean_prompt = v.text(prompt, "Question", 500, required=True)
    clean_answer = v.text(answer, "Fact", MAX_FACT_CHARS, required=status == "answered")
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        if conn.execute("SELECT COUNT(*) FROM section_facts WHERE section_id = ?",
                        (section_id,)).fetchone()[0] >= MAX_FACTS_PER_SECTION:
            raise v.ValidationError(f"A question can have at most {MAX_FACTS_PER_SECTION} facts.")
        cur = conn.execute(
            """INSERT INTO section_facts (section_id, prompt, answer, status, source, created_at, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (section_id, clean_prompt, clean_answer, status, source, now_iso(),
             now_iso() if status != "pending" else None),
        )
    return cur.lastrowid


def answer_section_fact(user_id: int, fact_id: int, answer: str | None) -> None:
    """Record the user's answer to a fact question; None means the user skipped it (unknown)."""
    clean = v.text(answer or "", "Fact", MAX_FACT_CHARS, required=answer is not None)
    status = "skipped" if answer is None else "answered"
    with connect() as conn:
        cur = conn.execute(
            """UPDATE section_facts SET answer = ?, status = ?, answered_at = ?
                WHERE id = ? AND section_id IN (SELECT s.id FROM application_sections s
                                                  JOIN applications a ON a.id = s.application_id
                                                 WHERE a.user_id = ?)""",
            (clean, status, now_iso(), fact_id, user_id),
        )
        if cur.rowcount == 0:
            raise NotFound("Fact not found.")


def delete_section_fact(user_id: int, fact_id: int) -> None:
    with connect() as conn:
        cur = conn.execute(
            """DELETE FROM section_facts WHERE id = ? AND section_id IN
                   (SELECT s.id FROM application_sections s JOIN applications a ON a.id = s.application_id
                     WHERE a.user_id = ?)""",
            (fact_id, user_id),
        )
        if cur.rowcount == 0:
            raise NotFound("Fact not found.")


def add_draft(user_id: int, section_id: int, text: str, mode: str, payload: dict) -> int:
    if mode not in ("live", "mock"):
        raise v.ValidationError("Invalid draft mode.")
    clean = v.text(text, "Draft", MAX_ANSWER_CHARS, required=True)
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        cur = conn.execute("INSERT INTO section_drafts (section_id, text, mode, payload, created_at) "
                           "VALUES (?, ?, ?, ?, ?)", (section_id, clean, mode, json.dumps(payload), now_iso()))
        conn.execute("""DELETE FROM section_drafts WHERE section_id = ? AND id NOT IN
                            (SELECT id FROM section_drafts WHERE section_id = ? ORDER BY id DESC LIMIT ?)""",
                     (section_id, section_id, MAX_DRAFTS_PER_SECTION))
    return cur.lastrowid


def latest_draft(user_id: int, section_id: int) -> dict | None:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        row = conn.execute("SELECT * FROM section_drafts WHERE section_id = ? ORDER BY id DESC LIMIT 1",
                           (section_id,)).fetchone()
    if row is None:
        return None
    draft = dict(row)
    draft["payload"] = json.loads(draft["payload"])
    return draft


def delete_drafts(user_id: int, section_id: int) -> None:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        conn.execute("DELETE FROM section_drafts WHERE section_id = ?", (section_id,))


def list_versions(user_id: int, section_id: int) -> list[dict]:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        rows = conn.execute("SELECT * FROM section_versions WHERE section_id = ? ORDER BY id DESC",
                            (section_id,)).fetchall()
    return [dict(r) for r in rows]


def restore_version(user_id: int, section_id: int, version_id: int) -> None:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        row = conn.execute("SELECT text FROM section_versions WHERE id = ? AND section_id = ?",
                           (version_id, section_id)).fetchone()
    if row is None:
        raise NotFound("Version not found.")
    save_section_answer(user_id, section_id, row["text"], source="restored")


def add_review(user_id: int, section_id: int, answer_hash: str, mode: str, payload: dict) -> int:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        cur = conn.execute("INSERT INTO section_reviews (section_id, answer_hash, mode, payload, created_at) "
                           "VALUES (?, ?, ?, ?, ?)", (section_id, answer_hash, mode, json.dumps(payload), now_iso()))
        conn.execute("""DELETE FROM section_reviews WHERE section_id = ? AND id NOT IN
                            (SELECT id FROM section_reviews WHERE section_id = ? ORDER BY id DESC LIMIT 10)""",
                     (section_id, section_id))
    return cur.lastrowid


def latest_review(user_id: int, section_id: int) -> dict | None:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        row = conn.execute("SELECT * FROM section_reviews WHERE section_id = ? ORDER BY id DESC LIMIT 1",
                           (section_id,)).fetchone()
    if row is None:
        return None
    review = dict(row)
    review["payload"] = json.loads(review["payload"])
    return review


MAX_PROPOSAL_REVIEWS = 10  # per application; older ones are pruned


def add_proposal_review(user_id: int, application_id: int, mode: str, snapshot: dict, payload: dict) -> int:
    """Store one whole-proposal review with the answers it reviewed (for before-and-after comparisons)."""
    if mode not in ("live", "mock"):
        raise v.ValidationError("Invalid review mode.")
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        cur = conn.execute("INSERT INTO proposal_reviews (application_id, mode, snapshot, payload, created_at) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (application_id, mode, json.dumps(snapshot), json.dumps(payload), now_iso()))
        conn.execute("""DELETE FROM proposal_reviews WHERE application_id = ? AND id NOT IN
                            (SELECT id FROM proposal_reviews WHERE application_id = ? ORDER BY id DESC LIMIT ?)""",
                     (application_id, application_id, MAX_PROPOSAL_REVIEWS))
    return cur.lastrowid


def list_proposal_reviews(user_id: int, application_id: int, limit: int = MAX_PROPOSAL_REVIEWS) -> list[dict]:
    """This application's proposal reviews, newest first. Another account's application raises NotFound."""
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        rows = conn.execute("SELECT * FROM proposal_reviews WHERE application_id = ? ORDER BY id DESC LIMIT ?",
                            (application_id, limit)).fetchall()
    reviews = []
    for row in rows:
        review = dict(row)
        review["snapshot"] = json.loads(review["snapshot"])
        review["payload"] = json.loads(review["payload"])
        reviews.append(review)
    return reviews


MAX_BUDGET_ITEMS = 100  # per application
MAX_BUDGET_NARRATIVES = 10  # per application; older ones are pruned
_BUDGET_FIELDS = ("category", "description", "quantity", "unit", "unit_cost_cents", "funding_source", "source_name",
                  "justification")


def _owned_budget_item(conn: sqlite3.Connection, user_id: int, item_id: int) -> sqlite3.Row:
    row = conn.execute("""SELECT b.* FROM budget_items b JOIN applications a ON a.id = b.application_id
                          WHERE b.id = ? AND a.user_id = ?""", (item_id, user_id)).fetchone()
    if row is None:
        raise NotFound("Budget line not found.")
    return row


def list_budget_items(user_id: int, application_id: int) -> list[dict]:
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        rows = conn.execute("SELECT * FROM budget_items WHERE application_id = ? ORDER BY position, id",
                            (application_id,)).fetchall()
    return [dict(r) for r in rows]


def add_budget_item(user_id: int, application_id: int, data: dict) -> int:
    item = v.budget_item(data)
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        count, last = conn.execute("SELECT COUNT(*), COALESCE(MAX(position), -1) FROM budget_items "
                                   "WHERE application_id = ?", (application_id,)).fetchone()
        if count >= MAX_BUDGET_ITEMS:
            raise v.ValidationError(f"A budget can have at most {MAX_BUDGET_ITEMS} lines.")
        cur = conn.execute(
            f"INSERT INTO budget_items (application_id, position, {', '.join(_BUDGET_FIELDS)}, updated_at) "
            f"VALUES (?, ?, {', '.join('?' * len(_BUDGET_FIELDS))}, ?)",
            (application_id, last + 1, *(item[f] for f in _BUDGET_FIELDS), now_iso()))
    return cur.lastrowid


def update_budget_item(user_id: int, item_id: int, data: dict) -> None:
    item = v.budget_item(data)
    with connect() as conn:
        _owned_budget_item(conn, user_id, item_id)
        conn.execute(f"UPDATE budget_items SET {', '.join(f + ' = ?' for f in _BUDGET_FIELDS)}, updated_at = ? "
                     "WHERE id = ?", (*(item[f] for f in _BUDGET_FIELDS), now_iso(), item_id))


def delete_budget_item(user_id: int, item_id: int) -> None:
    with connect() as conn:
        _owned_budget_item(conn, user_id, item_id)
        conn.execute("DELETE FROM budget_items WHERE id = ?", (item_id,))


def add_budget_narrative(user_id: int, application_id: int, mode: str, budget_hash: str, text: str,
                         payload: dict) -> int:
    if mode not in ("live", "mock"):
        raise v.ValidationError("Invalid narrative mode.")
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        cur = conn.execute("INSERT INTO budget_narratives (application_id, mode, budget_hash, text, payload, "
                           "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                           (application_id, mode, budget_hash, text, json.dumps(payload), now_iso()))
        conn.execute("""DELETE FROM budget_narratives WHERE application_id = ? AND id NOT IN
                            (SELECT id FROM budget_narratives WHERE application_id = ? ORDER BY id DESC LIMIT ?)""",
                     (application_id, application_id, MAX_BUDGET_NARRATIVES))
    return cur.lastrowid


def latest_budget_narrative(user_id: int, application_id: int) -> dict | None:
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        row = conn.execute("SELECT * FROM budget_narratives WHERE application_id = ? ORDER BY id DESC LIMIT 1",
                           (application_id,)).fetchone()
    if row is None:
        return None
    narrative = dict(row)
    narrative["payload"] = json.loads(narrative["payload"])
    return narrative


TIMELINE_STEPS = ("eligibility", "documents", "budget", "draft", "review", "revisions", "submission")
DEADLINE_SOURCES = ("grants.gov", "sample", "user")


def get_timeline(user_id: int, application_id: int) -> dict | None:
    """The application's workback plan with its milestones in order, or None."""
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        row = conn.execute("SELECT * FROM timelines WHERE application_id = ?", (application_id,)).fetchone()
        if row is None:
            return None
        milestones = conn.execute("SELECT * FROM timeline_milestones WHERE application_id = ? ORDER BY position",
                                  (application_id,)).fetchall()
    plan = dict(row)
    plan["settings"] = json.loads(plan["settings"])
    plan["milestones"] = [dict(m) for m in milestones]
    return plan


def save_timeline(user_id: int, application_id: int, deadline: str, deadline_source: str, settings: dict,
                  milestones: list[tuple[str, str]]) -> None:
    """Create or rebuild the plan from (step, due date) pairs. Steps already marked done stay done."""
    deadline = v.optional_date(deadline)
    if not deadline:
        raise v.ValidationError("A plan needs a deadline.")
    if deadline_source not in DEADLINE_SOURCES:
        raise v.ValidationError("Invalid deadline source.")
    steps = [step for step, _ in milestones]
    if sorted(steps) != sorted(TIMELINE_STEPS):
        raise v.ValidationError("A plan has each of the seven steps exactly once.")
    dated = [(step, v.optional_date(due)) for step, due in milestones]
    if not all(due for _, due in dated):
        raise v.ValidationError("Every step needs a date.")
    now = now_iso()
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        done = dict(conn.execute("SELECT step, done_at FROM timeline_milestones WHERE application_id = ? "
                                 "AND done_at IS NOT NULL", (application_id,)).fetchall())
        conn.execute("""INSERT INTO timelines (application_id, deadline, deadline_source, settings, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(application_id) DO UPDATE SET deadline = excluded.deadline,
                            deadline_source = excluded.deadline_source, settings = excluded.settings,
                            updated_at = excluded.updated_at""",
                     (application_id, deadline, deadline_source, json.dumps(settings), now, now))
        conn.execute("DELETE FROM timeline_milestones WHERE application_id = ?", (application_id,))
        conn.executemany("INSERT INTO timeline_milestones (application_id, position, step, due_date, done_at, edited, "
                         "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                         [(application_id, i, step, due, done.get(step), now) for i, (step, due) in enumerate(dated)])


def update_milestone(user_id: int, milestone_id: int, due_date, done: bool) -> None:
    """Change one milestone's date or mark it done. A changed date is remembered as edited by the user."""
    due = v.optional_date(due_date)
    if not due:
        raise v.ValidationError("Choose a date for this step.")
    with connect() as conn:
        row = conn.execute("""SELECT m.* FROM timeline_milestones m JOIN applications a ON a.id = m.application_id
                              WHERE m.id = ? AND a.user_id = ?""", (milestone_id, user_id)).fetchone()
        if row is None:
            raise NotFound("Milestone not found.")
        done_at = (row["done_at"] or now_iso()) if done else None
        edited = 1 if row["edited"] or due != row["due_date"] else 0
        conn.execute("UPDATE timeline_milestones SET due_date = ?, done_at = ?, edited = ?, updated_at = ? WHERE id = ?",
                     (due, done_at, edited, now_iso(), milestone_id))


def delete_timeline(user_id: int, application_id: int) -> None:
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        conn.execute("DELETE FROM timelines WHERE application_id = ?", (application_id,))  # milestones cascade


def list_open_milestones(user_id: int) -> list[dict]:
    """Every milestone not yet done across this user's applications, soonest first (for the dashboard)."""
    with connect() as conn:
        rows = conn.execute("""SELECT m.*, a.title AS application_title, t.deadline, t.deadline_source
                               FROM timeline_milestones m
                               JOIN applications a ON a.id = m.application_id
                               JOIN timelines t ON t.application_id = m.application_id
                               WHERE a.user_id = ? AND m.done_at IS NULL
                               ORDER BY m.due_date, m.position""", (user_id,)).fetchall()
    return [dict(r) for r in rows]


MAX_PURSUIT_ASSESSMENTS = 5  # per user and target; older ones are pruned
PURSUIT_OUTCOMES = ("strong", "verify", "caution", "do_not_pursue")


def add_pursuit_assessment(user_id: int, target: str, grant_id: str | None, application_id: int | None,
                           outcome: str, mode: str, payload: dict) -> int:
    if outcome not in PURSUIT_OUTCOMES or mode not in ("live", "mock"):
        raise v.ValidationError("Invalid assessment.")
    if not re.fullmatch(r"(?:grant:[a-z0-9\-]{1,40}|application:\d{1,12})", target or ""):
        raise v.ValidationError("Invalid assessment target.")
    with connect() as conn:
        if application_id is not None:
            _require_application(conn, user_id, application_id)
        if grant_id is not None and conn.execute("SELECT 1 FROM grants WHERE id = ?", (grant_id,)).fetchone() is None:
            raise NotFound("Grant not found.")
        cur = conn.execute("INSERT INTO pursuit_assessments (user_id, target, grant_id, application_id, outcome, mode, "
                           "payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (user_id, target, grant_id, application_id, outcome, mode, json.dumps(payload), now_iso()))
        conn.execute("""DELETE FROM pursuit_assessments WHERE user_id = ? AND target = ? AND id NOT IN
                            (SELECT id FROM pursuit_assessments WHERE user_id = ? AND target = ?
                             ORDER BY id DESC LIMIT ?)""",
                     (user_id, target, user_id, target, MAX_PURSUIT_ASSESSMENTS))
    return cur.lastrowid


def list_pursuit_assessments(user_id: int, target: str | None = None, limit: int = MAX_PURSUIT_ASSESSMENTS
                             ) -> list[dict]:
    """This user's assessments, newest first: of one target, or the latest of every target."""
    with connect() as conn:
        if target is not None:
            rows = conn.execute("SELECT * FROM pursuit_assessments WHERE user_id = ? AND target = ? "
                                "ORDER BY id DESC LIMIT ?", (user_id, target, limit)).fetchall()
        else:
            rows = conn.execute("""SELECT * FROM pursuit_assessments WHERE user_id = ? AND id IN
                                       (SELECT MAX(id) FROM pursuit_assessments WHERE user_id = ? GROUP BY target)
                                   ORDER BY id DESC LIMIT ?""", (user_id, user_id, limit)).fetchall()
    assessments = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        assessments.append(item)
    return assessments


MAX_SETTINGS_CHARS = 20_000
MAX_COMMITMENTS_PER_USER = 50
MAX_DRIFT_ASSESSMENTS = 3  # per user and grant; older ones are pruned


def get_capacity_settings(user_id: int) -> dict:
    """The user's saved capacity and priority settings ({} until they change one). portfolio.py validates them."""
    with connect() as conn:
        row = conn.execute("SELECT settings FROM capacity_settings WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["settings"]) if row else {}


def save_capacity_settings(user_id: int, settings: dict) -> None:
    text = json.dumps(settings)
    if len(text) > MAX_SETTINGS_CHARS:
        raise v.ValidationError("Too many settings.")
    with connect() as conn:
        conn.execute("""INSERT INTO capacity_settings (user_id, settings, updated_at) VALUES (?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET settings = excluded.settings,
                            updated_at = excluded.updated_at""", (user_id, text, now_iso()))


def list_commitments(user_id: int) -> list[dict]:
    """Work outside GrantBridge that takes the same staff hours (reports, renewals), soonest first."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM capacity_commitments WHERE user_id = ? ORDER BY due_date, id",
                            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def add_commitment(user_id: int, title: str, hours, due_date) -> int:
    clean_title = v.text(title, "Commitment", 120, required=True)
    clean_hours = v.decimal(hours, "Hours", places=1, lo=Decimal("0.5"), hi=Decimal("500"))
    due = v.optional_date(due_date)
    if not due:
        raise v.ValidationError("A commitment needs a due date.")
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM capacity_commitments WHERE user_id = ?", (user_id,)).fetchone()[0]
        if count >= MAX_COMMITMENTS_PER_USER:
            raise v.ValidationError(f"At most {MAX_COMMITMENTS_PER_USER} commitments.")
        cur = conn.execute("INSERT INTO capacity_commitments (user_id, title, hours, due_date, created_at) "
                           "VALUES (?, ?, ?, ?, ?)", (user_id, clean_title, float(clean_hours), due, now_iso()))
    return cur.lastrowid


def delete_commitment(user_id: int, commitment_id: int) -> None:
    with connect() as conn:
        cur = conn.execute("DELETE FROM capacity_commitments WHERE id = ? AND user_id = ?", (commitment_id, user_id))
        if cur.rowcount == 0:
            raise NotFound("Commitment not found.")


def add_drift_assessment(user_id: int, grant_id: str, input_hash: str, mode: str, payload: dict) -> int:
    if mode not in ("live", "mock"):
        raise v.ValidationError("Invalid assessment mode.")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM grants WHERE id = ?", (grant_id,)).fetchone() is None:
            raise NotFound("Grant not found.")
        cur = conn.execute("INSERT INTO drift_assessments (user_id, grant_id, input_hash, mode, payload, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (user_id, grant_id, input_hash, mode, json.dumps(payload),
                                                         now_iso()))
        conn.execute("""DELETE FROM drift_assessments WHERE user_id = ? AND grant_id = ? AND id NOT IN
                            (SELECT id FROM drift_assessments WHERE user_id = ? AND grant_id = ?
                             ORDER BY id DESC LIMIT ?)""",
                     (user_id, grant_id, user_id, grant_id, MAX_DRIFT_ASSESSMENTS))
    return cur.lastrowid


def latest_drift_assessment(user_id: int, grant_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM drift_assessments WHERE user_id = ? AND grant_id = ? ORDER BY id DESC "
                           "LIMIT 1", (user_id, grant_id)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["payload"] = json.loads(item["payload"])
    return item


def list_ticks(user_id: int, section_id: int) -> set[str]:
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        rows = conn.execute("SELECT item_key FROM verification_ticks WHERE section_id = ?", (section_id,)).fetchall()
    return {r["item_key"] for r in rows}


def set_tick(user_id: int, section_id: int, item_key: str, checked: bool) -> None:
    key = v.text(item_key, "Checklist item", 64, required=True)
    with connect() as conn:
        _require_section(conn, user_id, section_id)
        if checked:
            conn.execute("INSERT OR IGNORE INTO verification_ticks (section_id, item_key, created_at) VALUES (?, ?, ?)",
                         (section_id, key, now_iso()))
        else:
            conn.execute("DELETE FROM verification_ticks WHERE section_id = ? AND item_key = ?", (section_id, key))


# ---------------------------------------------------------------- advisor messages

def list_messages(user_id: int, limit: int = 200) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM (SELECT id, role, content, mode, payload, run_id, created_at FROM advisor_messages
                               WHERE user_id = ? ORDER BY id DESC LIMIT ?)
               ORDER BY id""",
            (user_id, limit),
        ).fetchall()
    messages = []
    for r in rows:
        m = dict(r)
        m["payload"] = json.loads(m["payload"] or "{}")
        messages.append(m)
    return messages


def add_message(user_id: int, role: str, content: str, *, mode: str = "live",
                payload: dict | None = None, run_id: int | None = None) -> int:
    if role not in ("user", "assistant"):
        raise v.ValidationError("Invalid message role.")
    if mode not in ("live", "mock"):
        raise v.ValidationError("Invalid message mode.")
    clean = v.text(content, "Message", MAX_MESSAGE_CHARS if role == "user" else 20_000, required=True)
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO advisor_messages (user_id, role, content, mode, payload, run_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, role, clean, mode, json.dumps(payload or {}), run_id, now_iso()),
        )
        conn.execute("""DELETE FROM advisor_messages WHERE user_id = ? AND id NOT IN
                            (SELECT id FROM advisor_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?)""",
                     (user_id, user_id, MAX_MESSAGES_PER_USER))
    return cur.lastrowid


def clear_messages(user_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM advisor_messages WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------- Can We Afford to Win? (award feasibility)

MAX_NOTICE_CHARS = 20_000  # a funder's notice or award terms, pasted or uploaded as text
AWARD_FIELDS = ("notice", "notice_name", "terms", "inputs", "explanation")
_TARGET_KEY = re.compile(r"^(?:grant:[a-z0-9\-]{1,40}|application:\d{1,12})$")


def _require_target(conn: sqlite3.Connection, user_id: int, target_key: str) -> None:
    """A grant in the catalog, or one of this user's own applications."""
    if not _TARGET_KEY.match(str(target_key)):
        raise v.ValidationError("Choose a grant or an application.")
    kind, _, ident = target_key.partition(":")
    if kind == "grant":
        if conn.execute("SELECT 1 FROM grants WHERE id = ?", (ident,)).fetchone() is None:
            raise NotFound("Grant not found.")
    elif conn.execute("SELECT 1 FROM applications WHERE id = ? AND user_id = ?", (int(ident), user_id)
                      ).fetchone() is None:
        raise NotFound("Application not found.")


def _award_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    for name in ("terms", "inputs", "explanation"):
        item[name] = json.loads(item[name] or "{}")
    return item


def get_award_feasibility(user_id: int, target_key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM award_feasibility WHERE user_id = ? AND target_key = ?",
                           (user_id, target_key)).fetchone()
    return _award_row(row) if row else None


def save_award_feasibility(user_id: int, target_key: str, **fields) -> None:
    """Create or update this user's analysis of one grant or application: only the fields given change."""
    unknown = set(fields) - set(AWARD_FIELDS)
    if unknown:
        raise v.ValidationError(f"Unknown fields: {sorted(unknown)}")
    values = {}
    for name, value in fields.items():
        if name == "notice":
            values[name] = v.text(value or "", "The funder's notice", MAX_NOTICE_CHARS)
        elif name == "notice_name":
            values[name] = v.text(value or "", "The notice's name", 200)
        else:
            text = json.dumps(value or {})
            if len(text) > MAX_SETTINGS_CHARS * 5:
                raise v.ValidationError("Too much data to save.")
            values[name] = text
    with connect() as conn:
        _require_target(conn, user_id, target_key)
        conn.execute("INSERT OR IGNORE INTO award_feasibility (user_id, target_key, updated_at) VALUES (?, ?, ?)",
                     (user_id, target_key, now_iso()))
        if values:
            sets = ", ".join(f"{name} = ?" for name in values)
            conn.execute(f"UPDATE award_feasibility SET {sets}, updated_at = ? WHERE user_id = ? AND target_key = ?",
                         (*values.values(), now_iso(), user_id, target_key))


def list_award_feasibility(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM award_feasibility WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
                            (user_id,)).fetchall()
    return [_award_row(r) for r in rows]


def get_finance_settings(user_id: int) -> dict:
    """The organization's own money facts for Can We Afford to Win? ({} until the user enters one)."""
    with connect() as conn:
        row = conn.execute("SELECT settings FROM finance_settings WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["settings"]) if row else {}


def save_finance_settings(user_id: int, settings: dict) -> None:
    text = json.dumps(settings)
    if len(text) > MAX_SETTINGS_CHARS:
        raise v.ValidationError("Too many settings.")
    with connect() as conn:
        conn.execute("""INSERT INTO finance_settings (user_id, settings, updated_at) VALUES (?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET settings = excluded.settings,
                            updated_at = excluded.updated_at""", (user_id, text, now_iso()))


def get_demo_state(user_id: int) -> dict:
    """What the sample data added to this account, and the profile it replaced ({} if none was loaded)."""
    with connect() as conn:
        row = conn.execute("SELECT payload FROM demo_state WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["payload"]) if row else {}


def save_demo_state(user_id: int, payload: dict) -> None:
    text = json.dumps(payload)
    if len(text) > MAX_SETTINGS_CHARS:
        raise v.ValidationError("Too much demo state.")
    with connect() as conn:
        conn.execute("""INSERT INTO demo_state (user_id, payload, created_at) VALUES (?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload,
                            created_at = excluded.created_at""", (user_id, text, now_iso()))


def clear_demo_state(user_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM demo_state WHERE user_id = ?", (user_id,))


MAX_SOLICITATION_CHARS = 400_000


def save_solicitation_import(user_id: int, payload: dict, sources: dict) -> int:
    """Store one reading of an uploaded solicitation. The files themselves are never written to disk."""
    body, text = json.dumps(payload), json.dumps(sources)
    if len(body) + len(text) > MAX_SOLICITATION_CHARS:
        raise v.ValidationError("That solicitation is too large to store.")
    with connect() as conn:
        cur = conn.execute("INSERT INTO solicitation_imports (user_id, payload, sources, created_at) "
                           "VALUES (?, ?, ?, ?)", (user_id, body, text, now_iso()))
        return cur.lastrowid


def latest_solicitation_import(user_id: int, application_id: int | None = None) -> dict | None:
    with connect() as conn:
        if application_id is None:
            row = conn.execute("SELECT * FROM solicitation_imports WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                               (user_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM solicitation_imports WHERE user_id = ? AND application_id = ? "
                               "ORDER BY id DESC LIMIT 1", (user_id, application_id)).fetchone()
    if row is None:
        return None
    return {**dict(row), "payload": json.loads(row["payload"]), "sources": json.loads(row["sources"])}


def link_solicitation_import(user_id: int, application_id: int, payload: dict) -> None:
    """Attach the most recent reading to the application the user imported it into."""
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        conn.execute("""UPDATE solicitation_imports SET application_id = ?
                         WHERE id = (SELECT id FROM solicitation_imports WHERE user_id = ?
                                      ORDER BY id DESC LIMIT 1) AND user_id = ?""",
                     (application_id, user_id, user_id))


def delete_solicitation_imports(user_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM solicitation_imports WHERE user_id = ?", (user_id,))


def fill_blank_application_fields(user_id: int, application_id: int, *, title: str | None = None,
                                  funder: str | None = None) -> list[str]:
    """Fill the title and funder only where they are still blank, and report which were filled.

    update_application deliberately does not touch these two, because they identify the application. The
    solicitation import needs to set them on a new application without ever overwriting what a user has typed.
    """
    with connect() as conn:
        row = conn.execute("SELECT title, funder FROM applications WHERE id = ? AND user_id = ?",
                           (application_id, user_id)).fetchone()
        if row is None:
            raise NotFound("Application not found.")
        filled = {}
        if title and not (row["title"] or "").strip():
            filled["title"] = v.text(title, "Application title", 200, required=True)
        if funder and not (row["funder"] or "").strip():
            filled["funder"] = v.text(funder, "Funder", 200)
        if filled:
            assignments = ", ".join(f"{k} = ?" for k in filled)
            conn.execute(f"UPDATE applications SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
                         (*filled.values(), now_iso(), application_id, user_id))
    return sorted(filled)


# ---------------------------------------------------------------- the proposal outline read from a solicitation

MAX_OUTLINE_SECTIONS = 40
MAX_OUTLINE_RESPONSE_CHARS = 40_000


def _owned_outline_section(conn: sqlite3.Connection, user_id: int, section_id: int) -> sqlite3.Row:
    row = conn.execute(
        """SELECT o.* FROM outline_sections o JOIN applications a ON a.id = o.application_id
            WHERE o.id = ? AND a.user_id = ?""", (section_id, user_id)).fetchone()
    if row is None:
        raise NotFound("Outline section not found.")
    return row


def _outline_row(row: sqlite3.Row) -> dict:
    out = dict(row)
    for key in ("elements", "evidence", "scored_by", "ticked"):
        out[key] = json.loads(out[key] or "[]")
    return out


def list_outline_sections(user_id: int, application_id: int) -> list[dict]:
    """The outline this application must be written to, in the funder's own order."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT o.* FROM outline_sections o JOIN applications a ON a.id = o.application_id
                WHERE o.application_id = ? AND a.user_id = ? ORDER BY o.position, o.id""",
            (application_id, user_id)).fetchall()
    return [_outline_row(r) for r in rows]


def add_outline_sections(user_id: int, application_id: int, sections: list[dict]) -> int:
    """Append confirmed outline sections to an application. Returns how many were written."""
    clean = []
    for section in sections:
        heading = v.text(section.get("heading", ""), "Section heading", 200, required=True)
        clean.append((heading, v.text(section.get("purpose", ""), "Section purpose", 400),
                      json.dumps(section.get("elements") or []), json.dumps(section.get("evidence") or []),
                      json.dumps(section.get("scored_by") or []), section.get("limit_words"),
                      section.get("limit_pages"), str(section.get("excerpt") or "")[:600]))
    if not clean:
        return 0
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        start = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM outline_sections "
                             "WHERE application_id = ?", (application_id,)).fetchone()[0]
        if start + len(clean) > MAX_OUTLINE_SECTIONS:
            raise v.ValidationError(f"An application can have at most {MAX_OUTLINE_SECTIONS} outline sections.")
        when = now_iso()
        conn.executemany(
            """INSERT INTO outline_sections (application_id, position, heading, purpose, elements, evidence,
                                             scored_by, limit_words, limit_pages, excerpt, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(application_id, start + i, *row, when, when) for i, row in enumerate(clean)])
    return len(clean)


def save_outline_response(user_id: int, section_id: int, text: str, status: str | None = None) -> None:
    """The applicant's own draft for one outline section."""
    body = v.text(text, "Section response", MAX_OUTLINE_RESPONSE_CHARS)
    with connect() as conn:
        _owned_outline_section(conn, user_id, section_id)
        if status is None:
            conn.execute("UPDATE outline_sections SET response = ?, updated_at = ? WHERE id = ?",
                         (body, now_iso(), section_id))
            return
        conn.execute("UPDATE outline_sections SET response = ?, status = ?, updated_at = ? WHERE id = ?",
                     (body, v.choice(status, OUTLINE_STATUSES, "Status", allow_blank=False),
                      now_iso(), section_id))


def set_outline_ticks(user_id: int, section_id: int, ticked: list[int]) -> None:
    """Which of a section's required elements the applicant says they have covered."""
    with connect() as conn:
        row = _owned_outline_section(conn, user_id, section_id)
        total = len(json.loads(row["elements"] or "[]"))
        clean = sorted({int(n) for n in ticked if isinstance(n, int) and 0 <= int(n) < total})
        conn.execute("UPDATE outline_sections SET ticked = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(clean), now_iso(), section_id))


def delete_outline_section(user_id: int, section_id: int) -> None:
    with connect() as conn:
        row = _owned_outline_section(conn, user_id, section_id)
        if (row["response"] or "").strip():
            raise v.ValidationError("Clear the draft first: a section with writing in it cannot be removed.")
        conn.execute("DELETE FROM outline_sections WHERE id = ?", (section_id,))


def save_application_outline(user_id: int, application_id: int, payload: dict) -> None:
    """The rubric, the filing list, the registrations and the format rules for one application."""
    body = json.dumps(payload)
    if len(body) > MAX_SOLICITATION_CHARS:
        raise v.ValidationError("That outline is too large to store.")
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        when = now_iso()
        conn.execute(
            """INSERT INTO application_outline (application_id, payload, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(application_id)
               DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at""",
            (application_id, body, when, when))


def get_application_outline(user_id: int, application_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT o.* FROM application_outline o JOIN applications a ON a.id = o.application_id
                WHERE o.application_id = ? AND a.user_id = ?""", (application_id, user_id)).fetchone()
    if row is None:
        return None
    return {"payload": json.loads(row["payload"]),
            "objective_ticks": json.loads(row["objective_ticks"] or "{}"),
            "component_state": json.loads(row["component_state"] or "{}"), "updated_at": row["updated_at"]}


def set_objective_ticks(user_id: int, application_id: int, criterion: int, covered: list[int]) -> None:
    """Which objectives of one scoring criterion the applicant says their draft covers."""
    with connect() as conn:
        row = conn.execute(
            """SELECT o.payload, o.objective_ticks FROM application_outline o
                 JOIN applications a ON a.id = o.application_id
                WHERE o.application_id = ? AND a.user_id = ?""", (application_id, user_id)).fetchone()
        if row is None:
            raise NotFound("This application has no outline yet.")
        criteria = json.loads(row["payload"]).get("criteria") or []
        if not 0 <= criterion < len(criteria):
            raise NotFound("Criterion not found.")
        total = len(criteria[criterion].get("objectives") or [])
        ticks = json.loads(row["objective_ticks"] or "{}")
        ticks[str(criterion)] = sorted({int(n) for n in covered if isinstance(n, int) and 0 <= int(n) < total})
        conn.execute("UPDATE application_outline SET objective_ticks = ?, updated_at = ? "
                     "WHERE application_id = ?", (json.dumps(ticks), now_iso(), application_id))


def set_component_state(user_id: int, application_id: int, component: int, state: str) -> None:
    """Whether one required form or attachment is not started, in hand, or not applicable here."""
    clean = v.choice(state, COMPONENT_STATES, "Status", allow_blank=False)
    with connect() as conn:
        row = conn.execute(
            """SELECT o.payload, o.component_state FROM application_outline o
                 JOIN applications a ON a.id = o.application_id
                WHERE o.application_id = ? AND a.user_id = ?""", (application_id, user_id)).fetchone()
        if row is None:
            raise NotFound("This application has no outline yet.")
        components = json.loads(row["payload"]).get("components") or []
        if not 0 <= component < len(components):
            raise NotFound("Component not found.")
        state_map = json.loads(row["component_state"] or "{}")
        state_map[str(component)] = clean
        conn.execute("UPDATE application_outline SET component_state = ?, updated_at = ? "
                     "WHERE application_id = ?", (json.dumps(state_map), now_iso(), application_id))


def delete_application_outline(user_id: int, application_id: int) -> None:
    """Remove the whole outline for one application, its sections included."""
    with connect() as conn:
        _require_application(conn, user_id, application_id)
        conn.execute("DELETE FROM outline_sections WHERE application_id = ?", (application_id,))
        conn.execute("DELETE FROM application_outline WHERE application_id = ?", (application_id,))
