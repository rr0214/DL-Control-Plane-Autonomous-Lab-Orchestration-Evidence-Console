"""Assemble the batch that goes to the safety gate. No LLM call lives here any more (the setup agent has it).

Every batch contains:
- the optimizer's pick inside the setup agent's search space, when there is one
- two boundary probes, so the Policy Kernel visibly blocks them:
    1. Hf candidate                    -> RESTRICTED_ELEMENT
    2. Run-088 exact repeat (Arc-Melt) -> DUPLICATE_CONDITION
- one review control, always appended: a control route whose SEM scan is ambiguous,
  so the human-in-the-loop card appears on screen. This is a demo device, not a model choice.
All ratios come from the optimizer (propose_alloy_ratios); nothing here writes stoichiometry.
"""
from __future__ import annotations

from typing import Callable

from .chemistry import normalize_composition, normalize_processing

MAX_PICKS = 1

# (elements, processing) routes. Each probe is resolved to ratios by the optimizer tool.
BOUNDARY_PROBES = [
    (["Nb", "Ti", "Hf", "Al"], "Additive/Anneal"),  # restricted element
    (["Nb", "Ti", "Cr", "Al"], "Arc-Melt"),         # exact Run-088 composition + processing
]

# Same composition as the Run-088 probe on a new route: the gate allows it, and its telemetry is Yellow.
YELLOW_CONTROL = (["Nb", "Ti", "Cr", "Al"], "Additive/Anneal")

ToolCall = Callable[[str, dict], tuple[dict, str]]


def _number(rows: list[dict]) -> list[dict]:
    return [dict(row, candidate_id=f"C-{i}", source="propose_alloy_ratios") for i, row in enumerate(rows, 1)]


def _key(row: dict) -> tuple[str, str]:
    return normalize_composition(row["composition"]), normalize_processing(row["processing"])


def _route_rows(call: ToolCall, elements: list[str], processing: str, origin: str, calls: list[dict]) -> list[dict]:
    output, transport = call("propose_alloy_ratios", {"elements": elements, "processing": processing, "n": 1})
    calls.append({"tool": "propose_alloy_ratios", "transport": transport, "args": {"elements": elements, "processing": processing}})
    return [{"composition": c["composition"], "processing": output["processing"], "origin": origin} for c in output["candidates"]]


def fixed_rows(call: ToolCall) -> tuple[list[dict], list[dict]]:
    """The two boundary probes and the review control, as (rows, tool_calls)."""
    calls: list[dict] = []
    rows: list[dict] = []
    for elements, processing in BOUNDARY_PROBES:
        rows.extend(_route_rows(call, elements, processing, "boundary_probe", calls))
    rows.extend(_route_rows(call, *YELLOW_CONTROL, "yellow_control", calls))
    return rows, calls


def space_rows(output: dict) -> list[dict]:
    """Optimizer output for a search space, as candidate rows."""
    return [{"composition": c["composition"], "processing": c["processing"], "origin": "optimizer"} for c in output.get("candidates", [])]


def pick(scored: list[dict], fixed: list[dict], history: list[dict]) -> list[dict]:
    """Choose the best-scored recipe, preferring one that is new to both the history and the fixed controls."""
    ranked = sorted(scored, key=lambda r: (r.get("expected_improvement") is None, -(r.get("expected_improvement") or 0)))
    unique: list[dict] = []
    seen: set = set()
    for row in ranked:
        if _key(row) not in seen:
            seen.add(_key(row))
            unique.append(row)
    known = {_key(r) for r in fixed} | {_key(r) for r in history}
    chosen = [r for r in unique if _key(r) not in known][:MAX_PICKS]
    # Never drop the pick silently: if it repeats something, the Policy Kernel blocks it and the trace shows it.
    return chosen or unique[:MAX_PICKS]


def assemble(chosen: list[dict], fixed: list[dict]) -> list[dict]:
    """Number the batch: the pick first, then the fixed rows (a fixed row the pick duplicates is removed)."""
    chosen_keys = {_key(r) for r in chosen}
    rest = [r for r in fixed if _key(r) not in chosen_keys]
    return _number(chosen + rest)
