"""The action gate (loop step 9). Plain code. The diagnosis agent only PROPOSES; this decides what is used.

The gate fails closed: anything it does not recognize or allow becomes "hold". It never releases a sample
and never changes a recipe or a policy; the only actions that exist are re-measure and hold, and in this
prototype even those are simulated (logged, not executed).
"""
from __future__ import annotations

from .history import clean_note

ALLOWED_ACTIONS = ("re-measure", "hold")
CAUSES = ("instrument", "material", "model")
MAX_REMEASURES = 2     # per sample, counted from the actions log
REASON_MAX = 300
SAFE_DEFAULT = "hold"


def gate(proposal: object, record: dict, prior_remeasures: int = 0) -> dict:
    """Returns {allowed, final_action, rule, detail, proposal}. allowed is False when the proposal was overridden."""
    p = proposal if isinstance(proposal, dict) else {}
    action, cause = p.get("action"), p.get("cause")
    reason = clean_note(p.get("reason") if isinstance(p.get("reason"), str) else "")
    if len(reason) > REASON_MAX:
        reason = reason[: REASON_MAX - 3] + "..."
    clean = {"action": action, "cause": cause, "reason": reason}

    def out(allowed: bool, final: str, rule: str | None, detail: str) -> dict:
        return {"allowed": allowed, "final_action": final, "rule": rule, "detail": detail, "proposal": clean}

    if action not in ALLOWED_ACTIONS or cause not in CAUSES or not reason:
        return out(False, SAFE_DEFAULT, "INVALID_PROPOSAL", "Proposal was not a valid action, cause and reason; held instead.")
    flags = (record.get("measurement_check") or {}).get("flags", [])
    if action == "re-measure" and (record.get("status") == "Red" or "restricted_element_absent" in flags):
        return out(False, SAFE_DEFAULT, "RED_HOLD_ONLY", "A Red sample or a restricted element can only be held, not re-measured.")
    if action == "re-measure" and prior_remeasures >= MAX_REMEASURES:
        return out(False, SAFE_DEFAULT, "REMEASURE_CAP", f"Already re-measured {prior_remeasures} times; held instead.")
    return out(True, action, None, "Allowed.")
