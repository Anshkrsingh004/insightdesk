"""SQLite layer. Annex C fixed schema (do not rename/remove required columns)
plus operational tables for conversations, audit (R11) and the Source Register.

Judges load their own accounts in the Annex C schema, so these column names and
types are a contract, not a suggestion.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .config import Settings, get_settings

# --- Annex C: fixed schema -------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id      TEXT PRIMARY KEY,   -- 'A' + 4 digits, e.g. A1001
    company_name    TEXT,
    owner_email     TEXT,               -- @example.com only; PII
    plan            TEXT,               -- Free | Pro | Business | Enterprise
    status          TEXT,               -- active | past_due | suspended | cancelled
    product_version TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS plan_limits (
    plan                 TEXT PRIMARY KEY,
    api_rate_limit_per_min INTEGER,
    monthly_workflow_runs  INTEGER,
    seats                INTEGER,
    support_tier         TEXT,
    monthly_price        REAL
);

CREATE TABLE IF NOT EXISTS usage (
    account_id          TEXT,
    period              TEXT,            -- YYYY-MM
    workflow_runs       INTEGER,
    api_calls_peak_per_min INTEGER,
    seats_used          INTEGER,
    PRIMARY KEY (account_id, period),
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id     TEXT PRIMARY KEY,
    account_id     TEXT,
    amount         REAL,                 -- > 0
    currency       TEXT,
    charged_on     TEXT,                 -- YYYY-MM-DD
    status         TEXT,                 -- paid | failed | refunded
    failure_reason TEXT,
    card_last4     TEXT,                 -- last 4 only, never full PAN
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

CREATE TABLE IF NOT EXISTS platform_status (
    component   TEXT PRIMARY KEY,        -- api | workflow-engine | connectors | billing
    status      TEXT,                    -- operational | degraded | outage
    incident_id TEXT,
    updated_at  TEXT                     -- ISO timestamp
);

CREATE TABLE IF NOT EXISTS policy_registry (
    rule_id        TEXT PRIMARY KEY,     -- e.g. REFUND-WINDOW-01
    description    TEXT,
    parameter      TEXT,                 -- e.g. refund_window_days, critic_min_groundedness
    operator       TEXT,                 -- <=, >=, ==, in
    value          TEXT,
    scope_plans    TEXT,                 -- ALL or comma list
    effective_from TEXT,
    source_id      TEXT,                 -- policy article in the Source Register
    source_section TEXT
);

CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id      TEXT PRIMARY KEY,
    conversation_id TEXT,
    account_id      TEXT,
    queue           TEXT,
    priority        TEXT,                -- low | normal | high | urgent
    created_at      TEXT,
    bundle_json     TEXT                 -- Annex D bundle, PII redacted
);

-- --- Operational tables (ours) ---------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id       TEXT PRIMARY KEY,
    doc_type        TEXT,
    title           TEXT,
    authority_level INTEGER,
    product_versions TEXT,
    last_updated    TEXT,
    effective_from  TEXT,
    deprecated_on   TEXT,
    supersedes      TEXT,
    provenance      TEXT,
    synthetic       TEXT,
    body            TEXT                 -- raw markdown / ticket text
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    account_id      TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    role            TEXT,                -- customer | assistant
    content         TEXT,
    answer_type     TEXT,
    route_json      TEXT,                -- nodes/routes taken
    trace_id        TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS audit_records (
    trace_id        TEXT PRIMARY KEY,
    conversation_id TEXT,
    account_id      TEXT,
    created_at      TEXT,
    record_json     TEXT                 -- full R11 audit record
);
"""


def get_conn(settings: Optional[Settings] = None) -> sqlite3.Connection:
    s = settings or get_settings()
    conn = sqlite3.connect(str(s.sqlite_abspath))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def connection(settings: Optional[Settings] = None) -> Iterator[sqlite3.Connection]:
    conn = get_conn(settings)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(settings: Optional[Settings] = None) -> None:
    s = settings or get_settings()
    Path(s.sqlite_abspath).parent.mkdir(parents=True, exist_ok=True)
    with connection(s) as conn:
        conn.executescript(SCHEMA)


def healthcheck(settings: Optional[Settings] = None) -> bool:
    try:
        with connection(settings) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
