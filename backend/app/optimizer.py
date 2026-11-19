"""The optimizer (loop step 3, ML, MOCK). It picks exact ratios; nothing else may write stoichiometry.

Two ways in, both through the MCP tool propose_alloy_ratios:
  - in_space(): the setup agent's search space (element ranges + routes) goes in, candidate recipes with
    exact ratios come out. Every ratio is inside the ranges.
  - fixed_route(): one element set and one route, used for the always-on boundary probes and the review control.

The ratios come from a fixed table standing in for a real optimizer (a Gaussian process or Bayesian search).
Swap the table for a real one without changing the interface. Scoring is NOT done here: see prediction_model.py.
"""
from __future__ import annotations

from .chemistry import elements_in, parse

BACKEND = "mock-optimizer-v1"
ALLOWED_PROCESSING = ("Arc-Melt", "Additive/Anneal")
MAX_SPACE_CANDIDATES = 6

# Stand-in output. Ratios are percent of each element and sum to 100. Mock values.
SURROGATE_TABLE = [
    {"composition": "Nb50-Ti20-Cr15-Al15"},
    {"composition": "Nb40-Ti25-Hf15-Al20"},
    # Added in S2 so a pick is rarely a repeat of the fixed controls. Mock values, no Hf.
    {"composition": "Nb45-Ti25-Cr20-Al10"},
    {"composition": "Nb42-Ti28-Cr18-Al12"},
    {"composition": "Nb46-Ti24-Cr17-Al13"},
    {"composition": "Nb44-Ti24-Cr16-Al12-Si4"},
    {"composition": "Nb40-Ti22-Cr14-Al12-Mo12"},
]

KNOWN_ELEMENTS = frozenset(e for r in SURROGATE_TABLE for e in elements_in(r["composition"]))


def fixed_route(elements: list[str], processing: str, n: int = 3) -> dict:
    if processing not in ALLOWED_PROCESSING:
        raise ValueError(f"processing must be one of {list(ALLOWED_PROCESSING)}")
    if not elements or not all(isinstance(e, str) for e in elements):
        raise ValueError("elements must be a non-empty list of element symbols")
    wanted = set(elements)
    n = max(1, min(int(n), 3))
    rows = [r for r in SURROGATE_TABLE if elements_in(r["composition"]) == wanted]
    return {
        "tool": "optimizer",
        "backend": BACKEND,
        "processing": processing,
        "candidates": [dict(r) for r in rows[:n]],
    }


def in_space(space: dict, n: int = MAX_SPACE_CANDIDATES) -> dict:
    """Candidates whose every element is allowed and whose every percent is inside that element's range."""
    routes = [r for r in space.get("routes", []) if r in ALLOWED_PROCESSING]
    ranges = {e["symbol"]: (e["min_pct"], e["max_pct"]) for e in space.get("elements", [])}
    if not routes or not ranges:
        raise ValueError("search space needs at least one element range and one allowed route")
    n = max(1, min(int(n), MAX_SPACE_CANDIDATES))
    rows: list[dict] = []
    for row in SURROGATE_TABLE:
        parts = parse(row["composition"])
        if all(el in ranges and ranges[el][0] <= pct <= ranges[el][1] for el, pct in parts.items()):
            rows.extend({"composition": row["composition"], "processing": route} for route in routes)
    return {"tool": "optimizer", "backend": BACKEND, "mode": "search_space", "candidates": rows[:n]}
