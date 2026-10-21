"""SQLite storage: one connection per operation, schema created on first use.

Schema changes are additive only (new tables / new nullable columns) so existing
user data is never dropped or rewritten by an upgrade.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from medione import config

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    recovery_hash TEXT,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    ai_consent_at TEXT,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'self',
    date_of_birth TEXT,
    sex TEXT,
    blood_group TEXT,
    phone TEXT,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    consent_statement TEXT,
    consent_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_profiles_user ON profiles(user_id);

CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'hospital',
    address TEXT,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    specialty TEXT,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
    phone TEXT,
    email TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_doctors_user ON doctors(user_id);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    record_date TEXT,
    end_date TEXT,
    doctor_id INTEGER REFERENCES doctors(id) ON DELETE SET NULL,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
    condition TEXT,
    summary TEXT,
    notes TEXT,
    follow_up_date TEXT,
    status TEXT,
    source TEXT NOT NULL DEFAULT 'patient',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_records_profile_date ON records(profile_id, record_date);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY,
    record_id INTEGER REFERENCES records(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    duration TEXT,
    route TEXT,
    instructions TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    uncertain INTEGER NOT NULL DEFAULT 0,
    uncertain_note TEXT
);
CREATE INDEX IF NOT EXISTS ix_meds_profile ON medications(profile_id);

CREATE TABLE IF NOT EXISTS lab_results (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    value_num REAL,
    value_text TEXT,
    unit TEXT,
    ref_low REAL,
    ref_high REAL,
    ref_text TEXT,
    uncertain INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_labs_profile ON lab_results(profile_id, test_name);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    record_id INTEGER REFERENCES records(id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    storage_name TEXT NOT NULL UNIQUE,
    extracted_text TEXT,
    ai_summary TEXT,
    ai_summary_at TEXT,
    uploaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_docs_profile ON documents(profile_id);
CREATE INDEX IF NOT EXISTS ix_docs_hash ON documents(profile_id, sha256);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    notes TEXT,
    due_date TEXT NOT NULL,
    time_of_day TEXT,
    repeat TEXT NOT NULL DEFAULT 'none',
    until_date TEXT,
    source_record_id INTEGER REFERENCES records(id) ON DELETE SET NULL,
    active INTEGER NOT NULL DEFAULT 1,
    last_done_on TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_dismissals (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    record_a INTEGER NOT NULL,
    record_b INTEGER NOT NULL,
    PRIMARY KEY (profile_id, record_a, record_b)
);

CREATE TABLE IF NOT EXISTS share_links (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    record_ids_json TEXT NOT NULL,
    include_summary INTEGER NOT NULL DEFAULT 0,
    include_files INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_access_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    profile_id INTEGER,
    action TEXT NOT NULL,
    target TEXT,
    detail TEXT,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_log(user_id, at);

-- v2: appointments, health concerns, home vitals, emergency card
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    starts_on TEXT NOT NULL,
    time_of_day TEXT,
    doctor_id INTEGER REFERENCES doctors(id) ON DELETE SET NULL,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
    purpose TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'consultation',
    status TEXT NOT NULL DEFAULT 'upcoming',
    questions TEXT,
    notes TEXT,
    outcome TEXT,
    record_id INTEGER REFERENCES records(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_appts_profile ON appointments(profile_id, starts_on);

CREATE TABLE IF NOT EXISTS health_concerns (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body_area TEXT,
    started_on TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    resolved_on TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS concern_logs (
    id INTEGER PRIMARY KEY,
    concern_id INTEGER NOT NULL REFERENCES health_concerns(id) ON DELETE CASCADE,
    logged_on TEXT NOT NULL,
    severity INTEGER NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS vitals (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    measured_on TEXT NOT NULL,
    time_of_day TEXT,
    value1 REAL NOT NULL,
    value2 REAL,
    context TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vitals_profile ON vitals(profile_id, kind, measured_on);

CREATE TABLE IF NOT EXISTS emergency_links (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_access_at TEXT
);

CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT);

-- v3: change history of records, emergency-card choices
CREATE TABLE IF NOT EXISTS record_history (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    user_id INTEGER,
    changed_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    changes_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_history_record ON record_history(record_id);

CREATE TABLE IF NOT EXISTS emergency_settings (
    profile_id INTEGER PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    include_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_initialised: set[str] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    path = config.settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    key = str(config.settings.db_path)
    if key in _initialised:
        return
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        elif row["version"] < SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
        conn.commit()
    finally:
        conn.close()
    _initialised.add(key)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    init_db()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
