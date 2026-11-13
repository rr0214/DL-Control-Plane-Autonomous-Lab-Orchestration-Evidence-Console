"""Pre-synthesis risk signals for a proposed recipe. This is a MOCK, clearly labeled as one.

It answers: "before anything is made, how risky is this recipe?" so a scientist can approve,
revise, or reject the recipe while it is still just a formula. In a real deployment this would be
a trained model (ductility, phase stability) plus a furnace safety check. Here it is a fixed,
deterministic lookup so the demo is fast and never changes between runs.

Deterministic on purpose: same recipe in, same signals out. No LLM, no randomness, no network.
"""
from __future__ import annotations

from .chemistry import elements_in, normalize_composition, normalize_processing
from .config import RESTRICTED_ELEMENTS

SOURCE = "mock pre-synthesis risk model (demo values, not a trained model)"
BASELINE_RUN = "Run-071"
REVIEW_BELOW = 0.80  # predicted ductility margin under this needs a scientist before synthesis
# Mock scale for display only: the margin is a ratio to the baseline run, so elongation = margin x baseline.
# The decision still uses the ratio. These percentages are demo values, not measurements.
BASELINE_ELONGATION_PCT = 3.0

DEFAULT_SIGNALS = {
    "predicted_ductility_margin": 0.92,
    "furnace_blast_radius": "low",
    "phase_stability": 0.96,
}

# Hand-set demo values keyed by (normalized composition, normalized processing).
# The demo control recipe (Run-088's composition on a new route) is the borderline, high-risk case.
MOCK_RISK = {
    (normalize_composition("Nb50-Ti20-Cr15-Al15"), normalize_processing("Additive/Anneal")): {
        "predicted_ductility_margin": 0.71,
        "furnace_blast_radius": "high",
        "phase_stability": 0.97,
    },
}


def ductility_label(margin: float) -> str:
    return "borderline" if margin < REVIEW_BELOW else "comfortable"


def risk_signals(composition: str, processing: str) -> dict:
    base = MOCK_RISK.get((normalize_composition(composition), normalize_processing(processing)), DEFAULT_SIGNALS)
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
