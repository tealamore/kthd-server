"""SQLite storage. One connection per request; schema is created on startup."""
import json
import os
import sqlite3
from datetime import datetime, timezone

from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    participant_id  TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL
);

-- Append-only: every consent / withdrawal is a new row. Latest row wins.
CREATE TABLE IF NOT EXISTS consents (
    consent_id      TEXT PRIMARY KEY,
    participant_id  TEXT NOT NULL REFERENCES participants(participant_id),
    consented       INTEGER NOT NULL,          -- 1 = consented, 0 = declined/withdrew
    consent_version TEXT NOT NULL,             -- which consent form text they saw
    occurred_at     TEXT,                      -- client-reported time
    received_at     TEXT NOT NULL,             -- server time (UTC)
    extra           TEXT                       -- optional JSON
);

-- One row per intervention opportunity (decision point).
CREATE TABLE IF NOT EXISTS decisions (
    decision_id        TEXT PRIMARY KEY,
    participant_id     TEXT NOT NULL REFERENCES participants(participant_id),
    client_decision_id TEXT,                   -- for safe retries from the app
    occurred_at        TEXT,
    received_at        TEXT NOT NULL,
    context            TEXT NOT NULL,          -- JSON blob of whatever the app sends
    available          INTEGER NOT NULL,       -- 0 = not randomized (e.g. driving)
    arm                TEXT NOT NULL,
    probability        REAL NOT NULL,          -- P(this arm) at selection time
    policy_version     TEXT NOT NULL,
    UNIQUE (participant_id, client_decision_id)
);

-- Exactly one reward per decision, whichever arm was picked.
CREATE TABLE IF NOT EXISTS rewards (
    decision_id  TEXT PRIMARY KEY REFERENCES decisions(decision_id),
    reward       REAL NOT NULL,
    occurred_at  TEXT,
    received_at  TEXT NOT NULL,
    extra        TEXT
);

CREATE INDEX IF NOT EXISTS idx_decisions_participant ON decisions(participant_id);
CREATE INDEX IF NOT EXISTS idx_consents_participant ON consents(participant_id);
"""


def db_path() -> str:
    return current_app.config["DATABASE_PATH"]


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(db_path())
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_json(value) -> str | None:
    return None if value is None else json.dumps(value)


def iso(dt) -> str | None:
    return None if dt is None else dt.isoformat()
