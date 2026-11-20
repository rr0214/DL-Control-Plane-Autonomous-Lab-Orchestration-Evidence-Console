"""Up-front target check (loop step 1, plain code, no LLM). Runs before any other step.

A target is impossible when it asks for more than the lab can make or measure. Impossible targets stop the run
here, before the setup agent, the optimizer or the lab do any work, so no recipe is ever picked for them.

Rules (every one that applies is reported):
  TEMP_ABOVE_LAB_LIMIT      service temperature above MAX_SERVICE_TEMP_C
  STRENGTH_ABOVE_LAB_LIMIT  yield strength above MAX_YIELD_STRENGTH_MPA

ILLUSTRATIVE DEMO LIMITS. In production a lab scientist sets these from what the lab can actually make and
measure. A value exactly at a limit is allowed; only values above it are flagged.
"""
from __future__ import annotations

# ILLUSTRATIVE DEMO LIMITS: a lab scientist would set these in production.
MAX_YIELD_STRENGTH_MPA = 2000
MAX_SERVICE_TEMP_C = 2200


def check(targets: dict | None) -> dict:
    """Returns {feasible, rule, rules, reason}. rule is the first violated rule, or None when the targets are possible."""
    t = targets or {}
    temp = float(t.get("service_temp_c", 0))
    strength = float(t.get("min_yield_strength_mpa", 0))
    problems: list[tuple[str, str]] = []
    if temp > MAX_SERVICE_TEMP_C:
        problems.append(("TEMP_ABOVE_LAB_LIMIT", f"service temperature {temp:g} C is above the {MAX_SERVICE_TEMP_C} C lab limit"))
    if strength > MAX_YIELD_STRENGTH_MPA:
        problems.append(("STRENGTH_ABOVE_LAB_LIMIT", f"yield strength {strength:g} MPa is above the {MAX_YIELD_STRENGTH_MPA} MPa lab limit"))
    limits = f"(illustrative demo limits: {MAX_YIELD_STRENGTH_MPA} MPa, {MAX_SERVICE_TEMP_C} C)"
    if problems:
        return {
            "feasible": False,
            "rule": problems[0][0],
            "rules": [p[0] for p in problems],
            "reason": "Impossible targets: " + "; ".join(p[1] for p in problems)
            + f" {limits}. The run stopped before any recipe was picked.",
        }
    return {
        "feasible": True,
        "rule": None,
        "rules": [],
        "reason": f"Targets are within what the lab can make and measure {limits}.",
    }
