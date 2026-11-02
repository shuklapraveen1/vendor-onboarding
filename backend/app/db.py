"""SQLite persistence.

WAL mode + one short-lived connection per unit of work lets the pipeline
worker thread write events while the SSE endpoint reads them concurrently.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from . import config

_init_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    status          TEXT NOT NULL,
    legal_name      TEXT,
    pan             TEXT,
    gstin           TEXT,
    contact_email   TEXT,
    current_version INTEGER NOT NULL DEFAULT 1,
    risk_score      INTEGER NOT NULL DEFAULT 0,
    decision_reason TEXT,
    decided_by      TEXT,
    portal_token    TEXT UNIQUE,
    vendor_code     TEXT,
    scenario_id     TEXT
);

CREATE TABLE IF NOT EXISTS submission_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,
    source        TEXT NOT NULL,
    data_json     TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (submission_id, version)
);

CREATE TABLE IF NOT EXISTS documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id  TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    version        INTEGER NOT NULL,
    slot           TEXT NOT NULL,
    filename       TEXT NOT NULL,
    path           TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    size_bytes     INTEGER NOT NULL,
    carried_over   INTEGER NOT NULL DEFAULT 0,
    extraction_json TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    submission_id   TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    status          TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    decision        TEXT,
    decision_reason TEXT,
    risk_score      INTEGER,
    findings_json   TEXT,
    summary_json    TEXT,
    engine_json     TEXT
);

CREATE TABLE IF NOT EXISTS run_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    stage       TEXT,
    type        TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (run_id, seq)
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    run_id        TEXT,
    created_at    TEXT NOT NULL,
    audience      TEXT NOT NULL,
    kind          TEXT NOT NULL,
    to_address    TEXT NOT NULL,
    subject       TEXT NOT NULL,
    body          TEXT NOT NULL,
    action_url    TEXT,
    engine        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id TEXT,
    ts            TEXT NOT NULL,
    actor         TEXT NOT NULL,
    action        TEXT NOT NULL,
    details_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor_master (
    vendor_code    TEXT PRIMARY KEY,
    legal_name     TEXT NOT NULL,
    pan            TEXT NOT NULL,
    gstin          TEXT,
    account_number TEXT,
    ifsc           TEXT,
    status         TEXT NOT NULL,
    source         TEXT NOT NULL,
    submission_id  TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_submission ON runs(submission_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_docs_submission ON documents(submission_id, version);
CREATE INDEX IF NOT EXISTS idx_messages_submission ON messages(submission_id);
CREATE INDEX IF NOT EXISTS idx_audit_submission ON audit_log(submission_id);
CREATE INDEX IF NOT EXISTS idx_vm_pan ON vendor_master(pan);
CREATE INDEX IF NOT EXISTS idx_vm_bank ON vendor_master(account_number, ifsc);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.ensure_dirs()
    with _init_lock:
        conn = _connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    out = dict(row)
    for key in list(out.keys()):
        if key.endswith("_json"):
            raw = out.pop(key)
            out[key[: -len("_json")]] = json.loads(raw) if raw else None
    return out


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)
