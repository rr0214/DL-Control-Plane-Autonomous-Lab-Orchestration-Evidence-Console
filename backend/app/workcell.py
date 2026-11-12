"""Simulated Workcell telemetry. Replace read_telemetry with real instrument feeds later."""
from __future__ import annotations

from .chemistry import normalize_composition, normalize_processing

DEFAULT_TELEMETRY = {"sem_cv_confidence": 0.95, "xrd_phase_match": 0.96, "crack_detected": False}

# Keyed by (normalized composition, normalized processing).
# This sample is Yellow because the SEM scan is ambiguous, not because the composition is new.
MOCK_TELEMETRY = {
    (normalize_composition("Nb50-Ti20-Cr15-Al15"), normalize_processing("Additive/Anneal")): {
        "sem_cv_confidence": 0.71,
        "xrd_phase_match": 0.97,
        "crack_detected": False,
    },
}


def read_telemetry(composition: str, processing: str) -> dict:
    key = (normalize_composition(composition), normalize_processing(processing))
    return dict(MOCK_TELEMETRY.get(key, DEFAULT_TELEMETRY))


def classify(telemetry: dict) -> str:
    if telemetry["crack_detected"] or telemetry["xrd_phase_match"] < 0.5:
        return "Red"
    if telemetry["sem_cv_confidence"] < 0.8:
        return "Yellow"
    return "Green"
