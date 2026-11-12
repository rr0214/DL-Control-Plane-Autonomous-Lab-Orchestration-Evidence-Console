"""SQLite access for campaign context, prior runs, and the lineage of plans and samples."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id    TEXT PRIMARY KEY,
    goal           TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    export_control TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    composition TEXT NOT NULL,
    processing  TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS plans (
    thread_id    TEXT PRIMARY KEY,
    campaign_id  TEXT NOT NULL,
    status       TEXT NOT NULL,
    llm_mode     TEXT,
    summary_json TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
    sample_id      TEXT PRIMARY KEY,
    thread_id      TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    candidate_id   TEXT,
    composition    TEXT,
    processing     TEXT,
    status         TEXT,
    decision       TEXT,
    intuition_note TEXT NOT NULL DEFAULT '',
    telemetry_json TEXT NOT NULL DEFAULT '{}',
    updated_at     TEXT NOT NULL
);
"""

SEED_CAMPAIGNS = [
    (
        "CAMP-014",
        "Raise oxidation resistance of Nb-Ti-Cr-Al alloys without losing the ductility of the Run-071 baseline.",
        "SDL-Internal",
        "ITAR",
    ),
]

SEED_RUNS = [
    ("Run-071", "CAMP-014", "Nb40-Ti30-Cr20-Al10", "Arc-Melt", "Green", "Single phase, clean microstructure"),
    ("Run-088", "CAMP-014", "Nb50-Ti20-Cr15-Al15", "Arc-Melt", "Red", "Cracked during cooldown"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany("INSERT OR IGNORE INTO campaigns VALUES (?, ?, ?, ?)", SEED_CAMPAIGNS)
    conn.executemany("INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?, ?, ?)", SEED_RUNS)
    conn.commit()
    return conn


def get_campaign(conn: sqlite3.Connection, campaign_id: str) -> dict:
    row = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown campaign {campaign_id}")
    return dict(row)


def get_runs(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT run_id, campaign_id, composition, processing, outcome, note "
        "FROM runs WHERE campaign_id = ? ORDER BY run_id",
        (campaign_id,),
    )
    return [dict(r) for r in rows]


def save_plan(conn: sqlite3.Connection, thread_id: str, campaign_id: str, summary: dict) -> None:
    now = _now()
    conn.execute(
        "INSERT INTO plans (thread_id, campaign_id, status, llm_mode, summary_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(thread_id) DO UPDATE SET status = excluded.status, llm_mode = excluded.llm_mode, "
        "summary_json = excluded.summary_json, updated_at = excluded.updated_at",
        (thread_id, campaign_id, summary["status"], summary.get("llm_mode"), json.dumps(summary, default=str), now, now),
    )
    conn.commit()


def save_sample(conn: sqlite3.Connection, thread_id: str, campaign_id: str, record: dict) -> None:
    conn.execute(
        "INSERT INTO samples (sample_id, thread_id, campaign_id, candidate_id, composition, processing, "
        "status, decision, intuition_note, telemetry_json, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(sample_id) DO UPDATE SET status = excluded.status, decision = excluded.decision, "
        "intuition_note = excluded.intuition_note, telemetry_json = excluded.telemetry_json, "
        "updated_at = excluded.updated_at",
        (
            record["sample_id"],
            thread_id,
            campaign_id,
            record.get("candidate_id"),
            record.get("composition"),
            record.get("processing"),
            record.get("status"),
            record.get("decision"),
            record.get("intuition_note", ""),
            json.dumps(record.get("telemetry", {})),
            _now(),
        ),
    )
    conn.commit()


def clear_campaign_lineage(conn: sqlite3.Connection, campaign_id: str) -> list[str]:
    """Delete plans and samples for one campaign. Returns the thread IDs that were removed.

    Seed campaigns and runs are not touched.
    """
    thread_ids = [
        r["thread_id"]
        for r in conn.execute("SELECT thread_id FROM plans WHERE campaign_id = ?", (campaign_id,)).fetchall()
    ]
    conn.execute("DELETE FROM samples WHERE campaign_id = ?", (campaign_id,))
    conn.execute("DELETE FROM plans WHERE campaign_id = ?", (campaign_id,))
    conn.commit()
    return thread_ids


def get_sample(conn: sqlite3.Connection, sample_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
    return dict(row) if row else None


def list_samples(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM samples WHERE campaign_id = ? ORDER BY updated_at DESC", (campaign_id,))
    return [dict(r) for r in rows]


def list_plans(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT thread_id, status, llm_mode, created_at, updated_at FROM plans "
        "WHERE campaign_id = ? ORDER BY created_at DESC",
        (campaign_id,),
    )
    return [dict(r) for r in rows]
