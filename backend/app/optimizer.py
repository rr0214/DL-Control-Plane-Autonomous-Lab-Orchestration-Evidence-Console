"""The bayesian_optimizer tool. The only permitted source of numeric composition ratios.

Both the mock orchestrator and the LLM orchestrator call this same function, so
the model never writes stoichiometry itself. Swap the table for a real surrogate
model (e.g. a Gaussian process over measured runs) without changing the interface.
"""
from __future__ import annotations

from .chemistry import elements_in

ALLOWED_PROCESSING = ("Arc-Melt", "Additive/Anneal")

# Stand-in surrogate output. Ratios are percent of each element and sum to 100.
SURROGATE_TABLE = [
    {"composition": "Nb50-Ti20-Cr15-Al15", "expected_improvement": 0.92},
    {"composition": "Nb40-Ti25-Hf15-Al20", "expected_improvement": 0.88},
]


def bayesian_optimizer(elements: list[str], processing: str, n: int = 3) -> dict:
    if processing not in ALLOWED_PROCESSING:
        raise ValueError(f"processing must be one of {list(ALLOWED_PROCESSING)}")
    if not elements or not all(isinstance(e, str) for e in elements):
        raise ValueError("elements must be a non-empty list of element symbols")

    wanted = set(elements)
    n = max(1, min(int(n), 3))
    rows = [r for r in SURROGATE_TABLE if elements_in(r["composition"]) == wanted]
    rows.sort(key=lambda r: r["expected_improvement"], reverse=True)
    return {
        "tool": "bayesian_optimizer",
        "backend": "mock-surrogate-v0",
        "processing": processing,
        "candidates": [dict(r) for r in rows[:n]],
    }


TOOL_SCHEMA = {
    "name": "bayesian_optimizer",
    "description": (
        "Returns numeric composition ratios (percent of each element, summing to 100) for an "
        "element set and processing route. This is the only permitted source of stoichiometry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "description": 'Element symbols, e.g. ["Nb", "Ti", "Cr", "Al"]',
            },
            "processing": {"type": "string", "enum": list(ALLOWED_PROCESSING)},
            "n": {"type": "integer", "minimum": 1, "maximum": 3},
        },
        "required": ["elements", "processing"],
    },
}
