"""Deterministic Policy Kernel. Plain code, no LLM, target latency under 50 ms."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .chemistry import elements_in, normalize_composition, normalize_processing
from .config import RESTRICTED_ELEMENTS


@dataclass
class Verdict:
    candidate_id: str
    allowed: bool
    rule: str | None
    reason: str
    latency_ms: float


def check(candidate: dict, history: list[dict]) -> Verdict:
    started = time.perf_counter()
    cid = candidate["candidate_id"]
    comp = candidate["composition"]
    proc = candidate["processing"]

    def done(allowed: bool, rule: str | None, reason: str) -> Verdict:
        return Verdict(cid, allowed, rule, reason, round((time.perf_counter() - started) * 1000, 3))

    restricted = sorted(elements_in(comp) & RESTRICTED_ELEMENTS)
    if restricted:
        return done(
            False,
            "RESTRICTED_ELEMENT",
            f"Contains restricted element {', '.join(restricted)}; blocked before any sample is made",
        )

    key = (normalize_composition(comp), normalize_processing(proc))
    for run in history:
        run_key = (normalize_composition(run["composition"]), normalize_processing(run["processing"]))
        if run_key == key:
            return done(
                False,
                "DUPLICATE_CONDITION",
                f"Same composition and processing as {run['run_id']} (outcome: {run['outcome']})",
            )

    return done(True, None, "Passed restricted-element and duplicate-condition checks")


def evaluate(candidates: list[dict], history: list[dict]) -> list[Verdict]:
    return [check(c, history) for c in candidates]
