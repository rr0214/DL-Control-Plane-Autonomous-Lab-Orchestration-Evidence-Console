"""The release checkpoint (loop step 11). A person decides; this file does the comparison and the rules.

Results are compared with the customer's targets. Two of the three comparisons use ESTIMATES from the
simulated measurements, not measurements, and the output says so on every row:
  - strength: yield strength estimated from hardness (about HV x 9.807 / 3, a common rule of thumb)
  - temperature: a mock correlation from oxidation mass gain to a service temperature (made up for the demo)
  - hafnium: the measured Hf (simulated EDS reading), so this one is a direct comparison

Rules (plain code):
  - A Red sample can never be released (RED_NO_RELEASE).
  - Releasing with an exception (a missed target, a Yellow status, or an open diagnosis hold) needs a written
    reason of at least MIN_NOTE characters (NOTE_REQUIRED). Withholding never needs one.
  - Only a role with the release permission can decide; that check is in the API.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .history import clean_note

__all__ = ["compare", "evaluate", "decide", "make_receipt", "clean_note", "MIN_NOTE", "DECISIONS"]

TABOR = 9.807 / 3            # MPa per HV
TEMP_BASE_C = 1500           # mock: service temperature at zero oxidation mass gain
TEMP_PER_MG_CM2 = 80         # mock: degrees lost per mg/cm2 of oxidation mass gain
MIN_NOTE = 10
DECISIONS = ("release", "withhold")


def compare(targets: dict, measurements: dict) -> dict:
    hv, ox = measurements["hardness_hv"], measurements["oxidation_mg_cm2"]
    hf = measurements["composition_at_pct"].get("Hf", 0.0)
    strength = round(hv * TABOR)
    temp = round(TEMP_BASE_C - TEMP_PER_MG_CM2 * ox)

    def row(key: str, label: str, requirement: str, value: float, unit: str, ok: bool, basis: str, margin: float) -> dict:
        return {"key": key, "label": label, "requirement": requirement, "value": value, "unit": unit, "passed": ok, "basis": basis, "margin": round(margin, 1)}

    rows = [
        row("service_temp_c", "High temperature performance", f"at least {targets['service_temp_c']} C", temp, "C", temp >= targets["service_temp_c"], "estimated (mock correlation from oxidation)", temp - targets["service_temp_c"]),
        row("min_yield_strength_mpa", "Strength", f"at least {targets['min_yield_strength_mpa']} MPa", strength, "MPa", strength >= targets["min_yield_strength_mpa"], "estimated (from hardness)", strength - targets["min_yield_strength_mpa"]),
        row("max_hafnium_at_pct", "Reduced hafnium", f"at most {targets['max_hafnium_at_pct']} at%", hf, "at%", hf <= targets["max_hafnium_at_pct"], "measured (simulated EDS)", targets["max_hafnium_at_pct"] - hf),
    ]
    return {"rows": rows, "all_met": all(r["passed"] for r in rows)}


def evaluate(targets: dict, sample: dict, diagnosis: dict | None) -> dict:
    """What the scientist sees before deciding. `sample` is a stored sample; `diagnosis` its actions-log row or None."""
    comparison = compare(targets, sample["measurements"])
    exceptions = [f"target_missed:{r['key']}" for r in comparison["rows"] if not r["passed"]]
    if sample["status"] == "Yellow":
        exceptions.append("status_yellow")
    if diagnosis and diagnosis.get("final_action") == "hold":
        exceptions.append("diagnosis_hold")
    return {
        "comparison": comparison,
        "exceptions": exceptions,
        "needs_note": bool(exceptions),
        "can_release": sample["status"] != "Red",
        "blocked_rule": "RED_NO_RELEASE" if sample["status"] == "Red" else None,
    }


def decide(evaluation: dict, decision: str, note: str) -> dict:
    """The rules. Returns {ok, rule, detail}."""
    if decision not in DECISIONS:
        return {"ok": False, "rule": "INVALID_DECISION", "detail": f"decision must be one of {DECISIONS}"}
    if decision == "withhold":
        return {"ok": True, "rule": None, "detail": "Withheld."}
    if not evaluation["can_release"]:
        return {"ok": False, "rule": "RED_NO_RELEASE", "detail": "A Red sample cannot be released."}
    if evaluation["needs_note"] and len(clean_note(note)) < MIN_NOTE:
        return {"ok": False, "rule": "NOTE_REQUIRED", "detail": f"Releasing with an exception ({', '.join(evaluation['exceptions'])}) needs a written reason of at least {MIN_NOTE} characters."}
    return {"ok": True, "rule": None, "detail": "Released."}


def make_receipt(sample: dict, targets: dict, evaluation: dict, decision: str, note: str, role: str) -> dict:
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "sample_id": sample["sample_id"],
        "composition": sample["composition"],
        "processing": sample["processing"],
        "targets": targets,
        "comparison": [{k: r[k] for k in ("key", "value", "passed", "basis")} for r in evaluation["comparison"]["rows"]],
        "exceptions": evaluation["exceptions"],
        "decision": decision,
        "note": clean_note(note),
        "signed_by_role": role,
        "recorded_at": recorded_at,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {
        "receipt_id": f"RCPT-REL-{digest[:12]}",
        "content_sha256": digest,
        "signed_by_role": role,
        "recorded_at": recorded_at,
        "note": "Role comes from the client header in this demo; it is not real authentication.",
        "payload": payload,
    }
