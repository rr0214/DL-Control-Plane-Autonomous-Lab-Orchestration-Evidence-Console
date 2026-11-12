"""SQLite access for campaign context and prior runs. Seeded with demo data on first connect."""
from __future__ import annotations

import sqlite3
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


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
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
