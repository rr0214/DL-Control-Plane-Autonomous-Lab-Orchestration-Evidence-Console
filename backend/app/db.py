"""SQLite access for campaign context, prior runs, and the lineage of plans and samples."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import db_path
from .targets import DEFAULT_TARGETS

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id    TEXT PRIMARY KEY,
    goal           TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    export_control TEXT NOT NULL,
    targets_json   TEXT NOT NULL DEFAULT '{}'
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
CREATE TABLE IF NOT EXISTS actions (
    action_id    TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    sample_id    TEXT NOT NULL,
    proposed_json TEXT NOT NULL,
    gate_json    TEXT NOT NULL,
    final_action TEXT NOT NULL,
    mode         TEXT NOT NULL,
    executed     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    release_id   TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    sample_id    TEXT NOT NULL,
    decision     TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    evaluation_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
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
    measurements_json TEXT NOT NULL DEFAULT '{}',
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
    # Older databases were created before targets existed: add the column in place.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(campaigns)")}
    if "targets_json" not in columns:
        conn.execute("ALTER TABLE campaigns ADD COLUMN targets_json TEXT NOT NULL DEFAULT '{}'")
    sample_cols = {row["name"] for row in conn.execute("PRAGMA table_info(samples)")}
    if "measurements_json" not in sample_cols:
        conn.execute("ALTER TABLE samples ADD COLUMN measurements_json TEXT NOT NULL DEFAULT '{}'")
    conn.executemany(
        "INSERT OR IGNORE INTO campaigns (campaign_id, goal, tenant, export_control) VALUES (?, ?, ?, ?)",
        SEED_CAMPAIGNS,
    )
    # Seed the illustrative default targets only where none are set yet.
    conn.execute(
        "UPDATE campaigns SET targets_json = ? WHERE campaign_id = 'CAMP-014' AND targets_json = '{}'",
        (json.dumps(DEFAULT_TARGETS),),
    )
    conn.executemany("INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?, ?, ?)", SEED_RUNS)
    conn.commit()
    return conn


def get_campaign(conn: sqlite3.Connection, campaign_id: str) -> dict:
    row = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown campaign {campaign_id}")
    campaign = dict(row)
    campaign["targets"] = json.loads(campaign.pop("targets_json") or "{}")
    return campaign


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
        "status, decision, intuition_note, telemetry_json, measurements_json, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(sample_id) DO UPDATE SET thread_id = excluded.thread_id, status = excluded.status, "
        "decision = excluded.decision, "
        "intuition_note = excluded.intuition_note, telemetry_json = excluded.telemetry_json, "
        "measurements_json = excluded.measurements_json, "
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
            json.dumps(record.get("telemetry") or {}),
            json.dumps({"measurements": record.get("measurements"), "check": record.get("measurement_check")})
            if record.get("measurements")
            else "{}",
            _now(),
        ),
    )
    conn.commit()


def save_action(conn: sqlite3.Connection, thread_id: str, campaign_id: str, sample_id: str, diagnosis: dict) -> None:
    """Append-only log of what the diagnosis agent proposed and what the gate did with it. Nothing is executed:
    `executed` stays 0 until a real workcell is wired in."""
    conn.execute(
        "INSERT INTO actions (action_id, thread_id, campaign_id, sample_id, proposed_json, gate_json, final_action, mode, executed, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?) ON CONFLICT(action_id) DO NOTHING",
        (
            f"ACT-{thread_id}-{sample_id}",
            thread_id,
            campaign_id,
            sample_id,
            json.dumps(diagnosis["gate"]["proposal"]),
            json.dumps({k: diagnosis["gate"][k] for k in ("allowed", "final_action", "rule", "detail")}),
            diagnosis["gate"]["final_action"],
            diagnosis["mode"],
            _now(),
        ),
    )
    conn.commit()


def save_release(conn: sqlite3.Connection, thread_id: str, campaign_id: str, sample_id: str, decision: str, note: str, evaluation: dict, receipt: dict) -> str:
    release_id = f"REL-{thread_id}-{sample_id}"
    conn.execute(
        "INSERT INTO releases (release_id, thread_id, campaign_id, sample_id, decision, note, evaluation_json, receipt_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (release_id, thread_id, campaign_id, sample_id, decision, note, json.dumps(evaluation), json.dumps(receipt), _now()),
    )
    conn.commit()
    return release_id


def _release_row(r: sqlite3.Row) -> dict:
    row = dict(r)
    row["evaluation"] = json.loads(row.pop("evaluation_json"))
    row["receipt"] = json.loads(row.pop("receipt_json"))
    return row


def get_release(conn: sqlite3.Connection, thread_id: str, sample_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM releases WHERE thread_id = ? AND sample_id = ?", (thread_id, sample_id)).fetchone()
    return _release_row(r) if r else None


def list_releases(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM releases WHERE campaign_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 50", (campaign_id,))
    return [_release_row(r) for r in rows]


def get_action(conn: sqlite3.Connection, thread_id: str, sample_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM actions WHERE thread_id = ? AND sample_id = ?", (thread_id, sample_id)).fetchone()
    return dict(r) if r else None


def plan_targets(conn: sqlite3.Connection, thread_id: str) -> dict | None:
    r = conn.execute("SELECT summary_json FROM plans WHERE thread_id = ?", (thread_id,)).fetchone()
    return (json.loads(r["summary_json"]).get("targets") if r else None) or None


def count_remeasures(conn: sqlite3.Connection, thread_id: str, sample_id: str) -> int:
    """Earlier re-measure actions for this sample in this plan. (Sample ids repeat across plans, so the plan is part of the key.)"""
    return conn.execute(
        "SELECT COUNT(*) FROM actions WHERE thread_id = ? AND sample_id = ? AND final_action = 're-measure'", (thread_id, sample_id)
    ).fetchone()[0]


def list_actions(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM actions WHERE campaign_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 50", (campaign_id,)):
        row = dict(r)
        row["proposed"] = json.loads(row.pop("proposed_json"))
        row["gate"] = json.loads(row.pop("gate_json"))
        row["executed"] = bool(row["executed"])
        out.append(row)
    return out


def clear_campaign_lineage(conn: sqlite3.Connection, campaign_id: str) -> list[str]:
    """Delete plans and samples for one campaign. Returns the thread IDs that were removed.

    Seed campaigns and runs are not touched.
    """
    thread_ids = [
        r["thread_id"]
        for r in conn.execute("SELECT thread_id FROM plans WHERE campaign_id = ?", (campaign_id,)).fetchall()
    ]
    conn.execute("DELETE FROM samples WHERE campaign_id = ?", (campaign_id,))
    conn.execute("DELETE FROM actions WHERE campaign_id = ?", (campaign_id,))
    conn.execute("DELETE FROM releases WHERE campaign_id = ?", (campaign_id,))
    conn.execute("DELETE FROM plans WHERE campaign_id = ?", (campaign_id,))
    conn.commit()
    return thread_ids


def _hydrate(row: sqlite3.Row) -> dict:
    """A sample row as a dict, with measurements and the measurement check unpacked from JSON."""
    sample = dict(row)
    packed = json.loads(sample.pop("measurements_json", None) or "{}")
    sample["measurements"] = packed.get("measurements")
    sample["measurement_check"] = packed.get("check")
    return sample


def get_sample(conn: sqlite3.Connection, sample_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
    return _hydrate(row) if row else None


def list_samples(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM samples WHERE campaign_id = ? ORDER BY updated_at DESC", (campaign_id,))
    return [_hydrate(r) for r in rows]


def recent_decided_samples(conn: sqlite3.Connection, campaign_id: str, limit: int) -> list[dict]:
    """Samples with a decision (a scientist's or the system's), newest first. Samples still waiting for review are left out."""
    rows = conn.execute(
        "SELECT * FROM samples WHERE campaign_id = ? AND decision IS NOT NULL ORDER BY updated_at DESC, rowid DESC LIMIT ?",
        (campaign_id, limit),
    )
    return [_hydrate(r) for r in rows]


def plan_usage(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    """Per-plan LLM usage records, newest first. Plans from before usage tracking come back with no records."""
    out = []
    for r in conn.execute(
        "SELECT thread_id, llm_mode, created_at, summary_json FROM plans WHERE campaign_id = ? ORDER BY created_at DESC",
        (campaign_id,),
    ):
        try:
            records = json.loads(r["summary_json"]).get("llm_usage", [])
        except ValueError:
            records = []
        out.append({"thread_id": r["thread_id"], "llm_mode": r["llm_mode"], "created_at": r["created_at"], "records": records})
    return out


def list_plans(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT thread_id, status, llm_mode, created_at, updated_at FROM plans "
        "WHERE campaign_id = ? ORDER BY created_at DESC",
        (campaign_id,),
    )
    return [dict(r) for r in rows]
