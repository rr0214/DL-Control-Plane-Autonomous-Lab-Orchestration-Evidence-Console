"""The measurement check (loop step 9). Plain code, no model. Three kinds of rule:

1. Fixed rules: readings must be physically sensible, and no restricted element may show up in the sample.
2. Recipe vs measured composition: each element within TOLERANCE_AT_PCT of the recipe.
3. Anomaly vs similar compositions: hardness and oxidation compared to prior samples whose composition is
   close to this one (seed runs and earlier samples). With no similar sample the check says it could not
   assess, and does not flag.

Severity: a failed fixed rule is Red; a composition mismatch or an anomaly is Yellow. The inputs are
simulated today; the rules are real.
"""
from __future__ import annotations

from .chemistry import parse
from .config import RESTRICTED_ELEMENTS

TOLERANCE_AT_PCT = 1.0           # max |measured - recipe| per element
UNEXPECTED_ELEMENT_AT_PCT = 0.5  # an element not in the recipe above this is unexpected
RESTRICTED_AT_PCT = 0.1          # any restricted element above this is a hard fail
SUM_RANGE = (98.0, 102.0)        # measured composition must add up to about 100
HARDNESS_RANGE_HV = (50.0, 1500.0)
SIMILAR_L1_AT_PCT = 20.0         # "similar" = summed absolute at% difference under this
HARDNESS_REL_TOL = 0.30
OXIDATION_REL_TOL = 0.50


def _l1(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(abs(a.get(el, 0.0) - b.get(el, 0.0)) for el in set(a) | set(b))


def _item(rule: str, passed: bool, detail: str, severity: str | None = None) -> dict:
    return {"rule": rule, "passed": passed, "detail": detail, "severity": None if passed else severity}


def run_checks(composition: str, measurements: dict, references: list[dict], sample_id: str | None = None) -> dict:
    """references: [{id, composition: {el: at%}, hardness_hv, oxidation_mg_cm2}]. Returns the check record."""
    recipe = parse(composition)
    measured = measurements["composition_at_pct"]
    hv, ox = measurements["hardness_hv"], measurements["oxidation_mg_cm2"]
    items: list[dict] = []

    total = sum(measured.values())
    sane = SUM_RANGE[0] <= total <= SUM_RANGE[1] and HARDNESS_RANGE_HV[0] <= hv <= HARDNESS_RANGE_HV[1] and ox >= 0
    items.append(_item("readings_valid", sane, f"composition sums to {total:.1f}%, hardness {hv:.0f} HV, oxidation {ox:.2f}", "Red"))

    bad = {el: v for el, v in measured.items() if el in RESTRICTED_ELEMENTS and v > RESTRICTED_AT_PCT}
    items.append(
        _item(
            "restricted_element_absent",
            not bad,
            f"restricted element measured: {bad}" if bad else "no restricted element measured",
            "Red",
        )
    )

    deviations = {el: round(measured.get(el, 0.0) - recipe.get(el, 0.0), 1) for el in set(recipe) | set(measured)}
    off = {
        el: d
        for el, d in deviations.items()
        if (el in recipe and abs(d) > TOLERANCE_AT_PCT) or (el not in recipe and abs(d) > UNEXPECTED_ELEMENT_AT_PCT)
    }
    items.append(
        _item(
            "composition_match",
            not off,
            f"outside tolerance (at%): {off}" if off else f"all elements within {TOLERANCE_AT_PCT} at% of the recipe",
            "Yellow",
        )
    )

    similar = [r for r in references if r.get("id") != sample_id and _l1(recipe, r["composition"]) <= SIMILAR_L1_AT_PCT]
    if not similar:
        items.append(_item("anomaly_vs_similar", True, "no similar composition to compare; not assessed"))
    else:
        mean_hv = sum(r["hardness_hv"] for r in similar) / len(similar)
        mean_ox = sum(r["oxidation_mg_cm2"] for r in similar) / len(similar)
        hv_dev, ox_dev = (hv - mean_hv) / mean_hv, (ox - mean_ox) / mean_ox
        anomalies = []
        if abs(hv_dev) > HARDNESS_REL_TOL:
            anomalies.append(f"hardness {hv_dev:+.0%} vs similar")
        if abs(ox_dev) > OXIDATION_REL_TOL:
            anomalies.append(f"oxidation {ox_dev:+.0%} vs similar")
        ids = ", ".join(r["id"] for r in similar)
        items.append(
            _item(
                "anomaly_vs_similar",
                not anomalies,
                (f"{'; '.join(anomalies)} ({ids})" if anomalies else f"within tolerance of {len(similar)} similar ({ids})"),
                "Yellow",
            )
        )

    failed = [i for i in items if not i["passed"]]
    severity = "Red" if any(i["severity"] == "Red" for i in failed) else ("Yellow" if failed else None)
    return {
        "mock_inputs": True,
        "checks": items,
        "flags": [i["rule"] for i in failed],
        "severity": severity,
        "similar": [r["id"] for r in similar],
    }
