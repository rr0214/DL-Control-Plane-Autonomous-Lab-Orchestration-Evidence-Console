"""The prediction model (loop step 4, ML, MOCK). It scores each candidate the optimizer proposed.

The score is a stand-in "expected improvement" from a fixed lookup, not a trained model. A real version
would be a model trained on measured runs. Unknown compositions get None, never a guess.
"""
from __future__ import annotations

from . import telemetry
from .chemistry import normalize_composition

BACKEND = "mock-prediction-v1"

MOCK_SCORES = {
    "Nb50-Ti20-Cr15-Al15": 0.92,
    "Nb40-Ti25-Hf15-Al20": 0.88,
    "Nb45-Ti25-Cr20-Al10": 0.90,
    "Nb42-Ti28-Cr18-Al12": 0.87,
    "Nb46-Ti24-Cr17-Al13": 0.85,
    "Nb44-Ti24-Cr16-Al12-Si4": 0.86,
    "Nb40-Ti22-Cr14-Al12-Mo12": 0.83,
}
_SCORES = {normalize_composition(k): v for k, v in MOCK_SCORES.items()}


def predict(composition: str) -> float | None:
    return _SCORES.get(normalize_composition(composition))


def score(rows: list[dict]) -> list[dict]:
    """Return copies of the rows with expected_improvement and the backend name filled in."""
    with telemetry.span("prediction.score", candidates=len(rows), backend=BACKEND) as sp:
        scored = [dict(r, expected_improvement=predict(r["composition"]), prediction_backend=BACKEND) for r in rows]
        telemetry.record_io(
            sp,
            input="\n".join(f"- {r['composition']} via {r.get('processing')}" for r in rows) or "no candidates",
            output="\n".join(f"- {r['composition']}: expected improvement {r['expected_improvement']}" for r in scored) or "no scores",
        )
        return scored
