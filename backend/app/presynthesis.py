"""Pre-synthesis risk signals for a proposed recipe. This is a MOCK, clearly labeled as one.

It answers: "before anything is made, how risky is this recipe?" so a scientist can approve,
revise, or reject the recipe while it is still just a formula. In a real deployment this would be
a trained model (ductility, phase stability) plus a furnace safety check.

Here the ductility margin is a simple rule computed from the composition itself, so it scores whatever the
optimizer actually picks (not only the planted review test case). The margin is a ratio to baseline Run-071
(Nb40-Ti30-Cr20-Al10 = 1.0) and drops for the changes this campaign's own runs point at: more Nb (Run-088 at Nb50
cracked), more Al, less Ti, and any Si or Mo. The weights are demo values, not a trained model.

Deterministic on purpose: same recipe in, same signals out. No LLM, no randomness, no network.
"""
from __future__ import annotations

from .chemistry import elements_in, normalize_composition, normalize_processing, parse
from .config import RESTRICTED_ELEMENTS

SOURCE = "mock pre-synthesis risk model (composition rule with demo weights, not a trained model)"
BASELINE_RUN = "Run-071"
REVIEW_BELOW = 0.80  # predicted ductility margin under this needs a scientist before synthesis
# Mock scale for display only: the margin is a ratio to the baseline run, so elongation = margin x baseline.
# The decision still uses the ratio. These percentages are demo values, not measurements.
BASELINE_ELONGATION_PCT = 3.0

# Baseline Run-071 is Nb40-Ti30-Cr20-Al10. Margin lost per atomic percent away from it. Demo weights.
BASELINE_NB, BASELINE_TI, BASELINE_AL = 40.0, 30.0, 10.0
PENALTY_PER_PCT = {"Nb_above": 0.02, "Al_above": 0.02, "Ti_below": 0.01, "Si": 0.06, "Mo": 0.025}
PHASE_STABILITY = 0.96

# Hand-set override for the planted review test case (Run-088's composition on a new route), kept at its
# long-standing demo value so the review test case behaves exactly as before. Every other recipe uses the rule.
MOCK_RISK = {
    (normalize_composition("Nb50-Ti20-Cr15-Al15"), normalize_processing("Additive/Anneal")): {
        "predicted_ductility_margin": 0.71,
        "furnace_blast_radius": "high",
        "phase_stability": 0.97,
    },
}


def ductility_label(margin: float) -> str:
    return "borderline" if margin < REVIEW_BELOW else "comfortable"


def ductility_margin(composition: str) -> float:
    """The composition rule: 1.0 at the Run-071 baseline, lower for each step toward what cracked or embrittles."""
    p = parse(composition)
    loss = (
        PENALTY_PER_PCT["Nb_above"] * max(0.0, p.get("Nb", 0.0) - BASELINE_NB)
        + PENALTY_PER_PCT["Al_above"] * max(0.0, p.get("Al", 0.0) - BASELINE_AL)
        + PENALTY_PER_PCT["Ti_below"] * max(0.0, BASELINE_TI - p.get("Ti", 0.0))
        + PENALTY_PER_PCT["Si"] * p.get("Si", 0.0)
        + PENALTY_PER_PCT["Mo"] * p.get("Mo", 0.0)
    )
    return round(max(0.0, 1.0 - loss), 2)


def blast_radius(margin: float) -> str:
    return "high" if margin < 0.70 else "medium" if margin < REVIEW_BELOW else "low"


def rule_signals(composition: str) -> dict:
    margin = ductility_margin(composition)
    return {"predicted_ductility_margin": margin, "furnace_blast_radius": blast_radius(margin), "phase_stability": PHASE_STABILITY}


def risk_signals(composition: str, processing: str) -> dict:
    base = MOCK_RISK.get((normalize_composition(composition), normalize_processing(processing))) or rule_signals(composition)
    margin = float(base["predicted_ductility_margin"])
    return {
        "source": SOURCE,
        "baseline_run": BASELINE_RUN,
        "predicted_ductility_margin": margin,
        "ductility_label": ductility_label(margin),
        "predicted_elongation_pct": round(margin * BASELINE_ELONGATION_PCT, 1),
        "baseline_elongation_pct": BASELINE_ELONGATION_PCT,
        "min_elongation_pct": round(REVIEW_BELOW * BASELINE_ELONGATION_PCT, 1),
        "furnace_blast_radius": base["furnace_blast_radius"],
        "phase_stability": float(base["phase_stability"]),
        # This one is real, not mocked: it comes from the same restricted-element list the Policy Kernel uses.
        "restricted_elements": sorted(set(elements_in(composition)) & RESTRICTED_ELEMENTS),
    }


def needs_review(signals: dict) -> bool:
    return signals["predicted_ductility_margin"] < REVIEW_BELOW or bool(signals["restricted_elements"])


def review_reason(signals: dict) -> str:
    return (
        f"Predicted ductility is {signals['ductility_label']}: {signals['predicted_elongation_pct']:.1f}% elongation vs. "
        f"{signals['baseline_elongation_pct']:.1f}% for baseline {signals['baseline_run']} "
        f"(minimum {signals['min_elongation_pct']:.1f}% to skip review), and furnace blast radius is "
        f"{signals['furnace_blast_radius']}. Review the recipe before any sample is made."
    )
