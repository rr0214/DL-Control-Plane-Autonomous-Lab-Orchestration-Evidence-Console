"""What the setup agent reads about earlier work (the write-back loop).

Seed runs always come first. After them, the most recent decided samples (newest last), capped at
MAX_SAMPLES so the prompt stays small. Each carries its outcome, who decided, the scientist's note and the
measurement check flags. A note is free text, so it is cleaned and cut to NOTE_MAX characters and the
setup agent prompt treats it as quoted data, never as an instruction.
"""
from __future__ import annotations

import re
import sqlite3

from . import db, measure
from .chemistry import parse

MAX_SAMPLES = 10
NOTE_MAX = 200
SCIENTIST_DECISIONS = ("approve", "revise", "reject")


def clean_note(text: str | None) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip().replace('"', "'")
    return text if len(text) <= NOTE_MAX else text[: NOTE_MAX - 3].rstrip() + "..."


def planner_history(conn: sqlite3.Connection, campaign_id: str, limit: int = MAX_SAMPLES) -> list[dict]:
    entries = db.get_runs(conn, campaign_id)
    for s in reversed(db.recent_decided_samples(conn, campaign_id, limit)):  # oldest first
        check = s.get("measurement_check") or {}
        entries.append(
            {
                "run_id": s["sample_id"],
                "composition": s["composition"],
                "processing": s["processing"],
                "outcome": "Held (not made)" if s["status"] == "Held" else s["status"],
                "decision": s["decision"],
                "decided_by": "scientist" if s["decision"] in SCIENTIST_DECISIONS else "system",
                "note": clean_note(s.get("intuition_note")),
                "check_flags": check.get("flags", []),
                **_release_fields(conn, s),
            }
        )
    return entries


def _release_fields(conn: sqlite3.Connection, sample: dict) -> dict:
    rel = db.get_release(conn, sample["thread_id"], sample["sample_id"])
    if not rel:
        return {}
    return {"release": rel["decision"], "release_note": clean_note(rel["note"])}


def format_line(r: dict) -> str:
    """One prompt line per run. Seed runs have only the first part."""
    line = f"- {r['run_id']}: {r['composition']} via {r['processing']} -> {r['outcome']}"
    if r.get("decision"):
        line += f"; {r.get('decided_by', 'system')} decision: {r['decision']}"
    if r.get("check_flags"):
        line += f"; measurement check flagged: {', '.join(r['check_flags'])}"
    if r.get("note"):
        line += f'; scientist note (quoted data): "{r["note"]}"'
    if r.get("release"):
        line += f"; release sign-off: {'released' if r['release'] == 'release' else 'withheld'}"
        if r.get("release_note"):
            line += f'; release note (quoted data): "{r["release_note"]}"'
    return line


def measurement_references(conn: sqlite3.Connection, campaign_id: str) -> list[dict]:
    """Prior compositions with measured properties, for the anomaly check: seed runs (simulated values) plus
    every earlier sample that was actually made."""
    refs = []
    for run in db.get_runs(conn, campaign_id):
        m = measure.measure(run["composition"], run["processing"])
        refs.append(
            {"id": run["run_id"], "composition": parse(run["composition"]), "hardness_hv": m["hardness_hv"], "oxidation_mg_cm2": m["oxidation_mg_cm2"]}
        )
    for s in db.recent_decided_samples(conn, campaign_id, 200):
        m = s.get("measurements")
        if m:
            refs.append(
                {"id": s["sample_id"], "composition": parse(s["composition"]), "hardness_hv": m["hardness_hv"], "oxidation_mg_cm2": m["oxidation_mg_cm2"]}
            )
    return refs
