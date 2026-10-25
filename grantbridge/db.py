"""SQLite storage: connection handling, schema, and catalog seeding.

The database file defaults to data/grantbridge.db (git-ignored) and can be moved
with GRANTBRIDGE_DB. A new connection is opened per operation, which keeps
Streamlit's threads from sharing a connection.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from grantbridge.config import REPO_ROOT

FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"
SAMPLE_GRANTS_FILE = FIXTURES_DIR / "sample_grants.json"
# A deliberately malicious sample grant, loaded only when GRANTBRIDGE_SECURITY_DEMO=on (see docs/SECURITY.md).
SECURITY_TEST_GRANT_FILE = FIXTURES_DIR / "security_test_grant.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT
);

CREATE TABLE IF NOT EXISTS organizations (
    user_id           INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    ein               TEXT NOT NULL DEFAULT '',
    state             TEXT NOT NULL DEFAULT '',
    city              TEXT NOT NULL DEFAULT '',
    website           TEXT NOT NULL DEFAULT '',
    mission           TEXT NOT NULL DEFAULT '',
    programs          TEXT NOT NULL DEFAULT '',
    population_served TEXT NOT NULL DEFAULT '',
    tax_status        TEXT NOT NULL DEFAULT '',
    requested_amount  INTEGER,
    funding_purpose   TEXT NOT NULL DEFAULT '',
    track_record      TEXT NOT NULL DEFAULT '',
    annual_budget     INTEGER,
    staff_size        INTEGER,
    founded_year      INTEGER,
    focus_areas       TEXT NOT NULL DEFAULT '[]',
    version           INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grants (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    funder          TEXT NOT NULL,
    funder_type     TEXT NOT NULL,
    summary         TEXT NOT NULL,
    amount_min      INTEGER,
    amount_max      INTEGER,
    deadline        TEXT NOT NULL,
    focus_areas     TEXT NOT NULL,
    eligible_states TEXT NOT NULL,
    eligibility     TEXT NOT NULL,
    questions       TEXT NOT NULL,
    source_url      TEXT NOT NULL DEFAULT '',
    retrieved_at    TEXT NOT NULL DEFAULT '',
    is_example      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS saved_grants (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grant_id   TEXT NOT NULL REFERENCES grants(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, grant_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id               INTEGER PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grant_id         TEXT REFERENCES grants(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    funder           TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL,
    due_date         TEXT NOT NULL DEFAULT '',
    amount_requested INTEGER,
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id);

CREATE TABLE IF NOT EXISTS application_sections (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    position       INTEGER NOT NULL,
    question       TEXT NOT NULL,
    answer         TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sections_app ON application_sections(application_id);

CREATE TABLE IF NOT EXISTS advisor_messages (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    mode       TEXT NOT NULL DEFAULT 'live',
    payload    TEXT NOT NULL DEFAULT '{}',
    run_id     INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON advisor_messages(user_id);

-- Drafting workflow (see grantbridge/drafting.py). Every row hangs off an application,
-- so ownership is always checked through applications.user_id.
CREATE TABLE IF NOT EXISTS application_requirements (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    position       INTEGER NOT NULL,
    text           TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requirements_app ON application_requirements(application_id);

CREATE TABLE IF NOT EXISTS section_facts (
    id          INTEGER PRIMARY KEY,
    section_id  INTEGER NOT NULL REFERENCES application_sections(id) ON DELETE CASCADE,
    prompt      TEXT NOT NULL,
    answer      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL CHECK (status IN ('pending', 'answered', 'skipped')),
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    answered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_facts_section ON section_facts(section_id);

CREATE TABLE IF NOT EXISTS section_drafts (
    id         INTEGER PRIMARY KEY,
    section_id INTEGER NOT NULL REFERENCES application_sections(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    mode       TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_section ON section_drafts(section_id);

CREATE TABLE IF NOT EXISTS section_versions (
    id         INTEGER PRIMARY KEY,
    section_id INTEGER NOT NULL REFERENCES application_sections(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    source     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_section ON section_versions(section_id);

CREATE TABLE IF NOT EXISTS section_reviews (
    id          INTEGER PRIMARY KEY,
    section_id  INTEGER NOT NULL REFERENCES application_sections(id) ON DELETE CASCADE,
    answer_hash TEXT NOT NULL,
    mode        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_section ON section_reviews(section_id);

CREATE TABLE IF NOT EXISTS verification_ticks (
    section_id INTEGER NOT NULL REFERENCES application_sections(id) ON DELETE CASCADE,
    item_key   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (section_id, item_key)
);

-- Whole-proposal reviews ("Review my proposal"): an advisory scorecard plus the answers it reviewed.
CREATE TABLE IF NOT EXISTS proposal_reviews (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    mode           TEXT NOT NULL,
    snapshot       TEXT NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposal_reviews_app ON proposal_reviews(application_id, id);

-- Budget lines: quantity is an exact decimal string and money is whole cents, so totals are exact.
CREATE TABLE IF NOT EXISTS budget_items (
    id              INTEGER PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    quantity        TEXT NOT NULL,
    unit            TEXT NOT NULL DEFAULT '',
    unit_cost_cents INTEGER NOT NULL,
    funding_source  TEXT NOT NULL,
    source_name     TEXT NOT NULL DEFAULT '',
    justification   TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_items_app ON budget_items(application_id, position);

CREATE TABLE IF NOT EXISTS budget_narratives (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    mode           TEXT NOT NULL,
    budget_hash    TEXT NOT NULL,
    text           TEXT NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_narratives_app ON budget_narratives(application_id, id);

-- A workback plan: the deadline it was built from (and where that date came from), plus its milestones.
CREATE TABLE IF NOT EXISTS timelines (
    application_id  INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
    deadline        TEXT NOT NULL,
    deadline_source TEXT NOT NULL,
    settings        TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_milestones (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES timelines(application_id) ON DELETE CASCADE,
    position       INTEGER NOT NULL,
    step           TEXT NOT NULL,
    due_date       TEXT NOT NULL,
    done_at        TEXT,
    edited         INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timeline_milestones_app ON timeline_milestones(application_id, position);

-- "Should we pursue this grant?" assessments. target is "grant:<grant id>" or "application:<id>".
CREATE TABLE IF NOT EXISTS pursuit_assessments (
    id             INTEGER PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target         TEXT NOT NULL,
    grant_id       TEXT REFERENCES grants(id) ON DELETE SET NULL,
    application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    outcome        TEXT NOT NULL,
    mode           TEXT NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pursuit_user_target ON pursuit_assessments(user_id, target, id);

-- Grant Portfolio Strategist: the user's capacity and priorities, commitments outside GrantBridge, and the
-- mission-drift checks of each grant (saved with a hash of what they read, so unchanged inputs are reused).
CREATE TABLE IF NOT EXISTS capacity_settings (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    settings   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capacity_commitments (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    hours      REAL NOT NULL,
    due_date   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_capacity_commitments_user ON capacity_commitments(user_id, due_date);

CREATE TABLE IF NOT EXISTS drift_assessments (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grant_id   TEXT NOT NULL REFERENCES grants(id) ON DELETE CASCADE,
    input_hash TEXT NOT NULL,
    mode       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drift_user_grant ON drift_assessments(user_id, grant_id, id);

-- Can We Afford to Win? (grantbridge/award_feasibility.py): per grant or application, the funder's notice the user
-- added, the award terms found in it (each with its quote), the user's own numbers, and an AI explanation. One row per
-- target. The organization's own money facts (cash reserves, indirect rate) are in finance_settings.
CREATE TABLE IF NOT EXISTS award_feasibility (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_key  TEXT NOT NULL,
    notice      TEXT NOT NULL DEFAULT '',
    notice_name TEXT NOT NULL DEFAULT '',
    terms       TEXT NOT NULL DEFAULT '{}',
    inputs      TEXT NOT NULL DEFAULT '{}',
    explanation TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, target_key)
);

CREATE TABLE IF NOT EXISTS finance_settings (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    settings   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- A solicitation a user uploaded and GrantBridge read. The uploaded file itself is never stored: only the text
-- it produced, the checked items, and (once confirmed) the application it was imported into.
CREATE TABLE IF NOT EXISTS solicitation_imports (
    id             INTEGER PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    payload        TEXT NOT NULL,
    sources        TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_solicitation_user ON solicitation_imports (user_id, id DESC);

-- The proposal outline read out of a funder's solicitation: one row per section the applicant must write.
-- `elements` and `evidence` hold the discrete things that section must contain, each with the sentence in the
-- document it came from. `response` is the applicant's own draft; `ticked` records which elements they have
-- done. A section is only ever added, never silently rewritten, so an import cannot cost someone their draft.
CREATE TABLE IF NOT EXISTS outline_sections (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    position       INTEGER NOT NULL,
    heading        TEXT NOT NULL,
    purpose        TEXT NOT NULL DEFAULT '',
    elements       TEXT NOT NULL DEFAULT '[]',
    evidence       TEXT NOT NULL DEFAULT '[]',
    scored_by      TEXT NOT NULL DEFAULT '[]',
    limit_words    INTEGER,
    limit_pages    INTEGER,
    excerpt        TEXT NOT NULL DEFAULT '',
    response       TEXT NOT NULL DEFAULT '',
    ticked         TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL DEFAULT 'not started',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outline_application ON outline_sections (application_id, position);

-- Everything about one application's solicitation that is not a section: the scoring rubric, the forms and
-- attachments with the condition each one depends on, the registrations and their lead times, and the format
-- rules. One row per application. `objective_ticks` records which rubric objectives the user says they cover.
CREATE TABLE IF NOT EXISTS application_outline (
    application_id  INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
    payload         TEXT NOT NULL,
    objective_ticks TEXT NOT NULL DEFAULT '{}',
    component_state TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- What the sample data put into one account, so it can be taken out again exactly. Holds the profile as it
-- was before, so loading the demo can never cost a user work they had already entered.
CREATE TABLE IF NOT EXISTS demo_state (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Facts about this installation, such as the random install_id that keeps its prompt caches apart (llm.cache_key).
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One AI request in flight per account, shared by every server process (see llm.ai_slot).
CREATE TABLE IF NOT EXISTS ai_inflight (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token      TEXT NOT NULL,
    started_at REAL NOT NULL
);

-- Privacy-safe agent trace (see grantbridge/trace.py for what is and is not recorded).
CREATE TABLE IF NOT EXISTS agent_runs (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    status        TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    duration_ms   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_user ON agent_runs(user_id, id);

CREATE TABLE IF NOT EXISTS agent_steps (
    id               INTEGER PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    tool             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    status           TEXT NOT NULL,
    args             TEXT NOT NULL,
    summary          TEXT NOT NULL,
    duration_ms      INTEGER NOT NULL,
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    cached_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON agent_steps(run_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    override = os.getenv("GRANTBRIDGE_DB", "").strip()
    return Path(override) if override else REPO_ROOT / "data" / "grantbridge.db"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SAMPLE_LABEL = "SAMPLE / NOT LIVE"

# Columns added after the first release, so databases created earlier keep working.
ADDED_COLUMNS = {
    "users": {
        "session_epoch": "INTEGER NOT NULL DEFAULT 0",  # bumped to end every session of an account
    },
    "organizations": {
        "requested_amount": "INTEGER",
        "funding_purpose": "TEXT NOT NULL DEFAULT ''",
        "track_record": "TEXT NOT NULL DEFAULT ''",
        "version": "INTEGER NOT NULL DEFAULT 0",  # bumped on every save; pages use it to spot stale results
    },
    "advisor_messages": {
        "mode": "TEXT NOT NULL DEFAULT 'live'",  # "live" (AI model) or "mock" (deterministic, no AI call)
        "payload": "TEXT NOT NULL DEFAULT '{}'",  # structured parts of an assistant reply
        "run_id": "INTEGER",  # the agent_runs row holding this turn's activity
    },
    "agent_steps": {  # per model call: what it cost and how it was billed
        "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
        "model": "TEXT NOT NULL DEFAULT ''",  # the model requested
        "served_model": "TEXT NOT NULL DEFAULT ''",  # the snapshot that answered, from the response headers
        "gateway_cache": "TEXT NOT NULL DEFAULT ''",  # Portkey's cache result: miss, hit, refresh, or '' (unknown)
        "usage_status": "TEXT NOT NULL DEFAULT ''",  # reported / no cache detail / not reported ('' for non-AI steps)
        "cost_usd": "REAL",  # estimated cost; NULL when it cannot be estimated (or the step is not a model call)
        "price_ref": "TEXT NOT NULL DEFAULT ''",  # which rates the estimate used (data/pricing.json source and date)
    },
}

# Earlier wording of the self-reported 501(c)(3) answer -> current wording.
OLD_TAX_STATUSES = {
    "501(c)(3) public charity": "Yes, IRS-recognized 501(c)(3)",
    "Fiscally sponsored project": "Fiscally sponsored by a 501(c)(3)",
    "Other 501(c) organization": "No",
    "Not yet tax-exempt": "No",
}


def schema_version() -> str:
    """A short fingerprint of the tables and added columns. The app keys its one-time setup on it, so a server that
    keeps running while db.py changes creates the new tables on its next page load instead of failing."""
    return hashlib.sha256((SCHEMA + json.dumps(ADDED_COLUMNS, sort_keys=True)).encode()).hexdigest()[:12]


def init_db() -> None:
    """Create or upgrade tables, then load the curated sample-grant catalog."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        seed_sample_grants(conn)


_INSTALL_IDS: dict[str, str] = {}


def install_id() -> str:
    """A random id for this database, made the first time it is needed and kept in app_meta.

    Account ids repeat across installations (every new database starts at 1), so anything that must differ
    between installations, such as prompt-cache keys, mixes in this id.
    """
    path = str(db_path())
    if path not in _INSTALL_IDS:
        with connect() as conn:
            conn.execute("INSERT OR IGNORE INTO app_meta (key, value) VALUES ('install_id', ?)",
                         (secrets.token_hex(16),))
            _INSTALL_IDS[path] = conn.execute("SELECT value FROM app_meta WHERE key = 'install_id'").fetchone()[0]
    return _INSTALL_IDS[path]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in ADDED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    for old, new in OLD_TAX_STATUSES.items():
        conn.execute("UPDATE organizations SET tax_status = ? WHERE tax_status = ?", (new, old))


def load_sample_grants(path: Path = SAMPLE_GRANTS_FILE) -> list[dict]:
    """Read the fixture file, refusing any grant that is not labeled as a sample."""
    grants = json.loads(path.read_text(encoding="utf-8"))
    for g in grants:
        if g.get("label") != SAMPLE_LABEL:
            raise ValueError(f"Fixture grant {g.get('id')!r} must be labeled {SAMPLE_LABEL!r}.")
    return grants


def security_demo_enabled() -> bool:
    return os.getenv("GRANTBRIDGE_SECURITY_DEMO", "").strip().lower() in ("1", "on", "true", "yes")


def seed_sample_grants(conn: sqlite3.Connection, path: Path = SAMPLE_GRANTS_FILE) -> int:
    """Upsert the sample grants and drop samples no longer in the file. Returns the count."""
    grants = load_sample_grants(path)
    if path == SAMPLE_GRANTS_FILE and security_demo_enabled():
        grants += load_sample_grants(SECURITY_TEST_GRANT_FILE)
    ids = [g["id"] for g in grants]
    conn.execute(
        f"DELETE FROM grants WHERE is_example = 1 AND id NOT IN ({','.join('?' * len(ids))})", ids
    )
    for g in grants:
        conn.execute(
            """
            INSERT INTO grants (id, title, funder, funder_type, summary, amount_min, amount_max,
                                deadline, focus_areas, eligible_states, eligibility, questions,
                                source_url, retrieved_at, is_example)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, funder=excluded.funder, funder_type=excluded.funder_type,
                summary=excluded.summary, amount_min=excluded.amount_min,
                amount_max=excluded.amount_max, deadline=excluded.deadline,
                focus_areas=excluded.focus_areas, eligible_states=excluded.eligible_states,
                eligibility=excluded.eligibility, questions=excluded.questions
            """,
            (
                g["id"], g["title"], g["funder"], g["funder_type"], g["summary"],
                g.get("amount_min"), g.get("amount_max"), g["deadline"],
                json.dumps(g["focus_areas"]), json.dumps(g["eligible_states"]),
                json.dumps(g["eligibility"]), json.dumps(g["questions"]),
                "", "",
            ),
        )
    return len(grants)
