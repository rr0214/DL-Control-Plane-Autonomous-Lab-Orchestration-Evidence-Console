"""Candidate proposal. Real LLM tool-calling when ANTHROPIC_API_KEY is set, mock plan otherwise.

In both modes:
- every composition ratio comes from bayesian_optimizer (the model never writes stoichiometry)
- two boundary probes are always appended, so the Policy Kernel visibly blocks them:
    1. Hf candidate                      -> RESTRICTED_ELEMENT
    2. Run-088 exact repeat (Arc-Melt)   -> DUPLICATE_CONDITION
"""
from __future__ import annotations

import json

from .chemistry import normalize_composition, normalize_processing
from .config import anthropic_key, anthropic_model
from .optimizer import TOOL_SCHEMA, bayesian_optimizer

MAX_LLM_CANDIDATES = 2

BOUNDARY_PROBES = [
    (["Nb", "Ti", "Hf", "Al"], "Additive/Anneal"),  # restricted element
    (["Nb", "Ti", "Cr", "Al"], "Arc-Melt"),         # exact Run-088 composition + processing
]

# Same composition as the Run-088 probe, different processing route: the gate should allow it.
ALLOWED_CONTROL = (["Nb", "Ti", "Cr", "Al"], "Additive/Anneal")

SYSTEM_PROMPT = (
    "You are the campaign planner for an autonomous materials lab. You never write "
    "stoichiometry yourself. To propose a composition you call the bayesian_optimizer tool "
    "with an element set and a processing route, and you may only use the ratios it returns. "
    "Make two tool calls in total. Explore new compositions: do not use the restricted element Hf "
    "and do not repeat a prior run. The policy team adds its own boundary checks separately, "
    "so do not try to include them. Keep any text reply to one sentence."
)


def _rows(output: dict, origin: str) -> list[dict]:
    return [
        {
            "composition": c["composition"],
            "processing": output["processing"],
            "expected_improvement": c["expected_improvement"],
            "origin": origin,
        }
        for c in output.get("candidates", [])
    ]


def _number(rows: list[dict]) -> list[dict]:
    return [dict(row, candidate_id=f"C-{i}", source="bayesian_optimizer") for i, row in enumerate(rows, 1)]


def _run_tool(name: str, args: dict) -> dict:
    if name != "bayesian_optimizer":
        return {"error": f"unknown tool: {name}"}
    try:
        return bayesian_optimizer(**args)
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}


def _probe_rows() -> list[dict]:
    rows: list[dict] = []
    for elements, processing in BOUNDARY_PROBES:
        rows.extend(_rows(bayesian_optimizer(elements, processing, n=1), origin="boundary_probe"))
    return rows


def _propose_anthropic(goal: str, history: list[dict], key: str) -> tuple[list[dict], int]:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    prior = "\n".join(
        f"- {r['run_id']}: {r['composition']} via {r['processing']} -> {r['outcome']}" for r in history
    )
    messages = [
        {
            "role": "user",
            "content": f"Campaign goal: {goal}\nPrior runs:\n{prior}\n\nPropose two new candidate routes now.",
        }
    ]
    rows: list[dict] = []
    turns = 0
    for _ in range(4):
        response = client.messages.create(
            model=anthropic_model(),
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[TOOL_SCHEMA],
            messages=messages,
        )
        turns += 1
        messages.append({"role": "assistant", "content": response.content})
        uses = [block for block in response.content if block.type == "tool_use"]
        if not uses:
            break
        results = []
        for use in uses:
            output = _run_tool(use.name, use.input)
            rows.extend(_rows(output, origin="llm"))
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(output)})
        messages.append({"role": "user", "content": results})
    return rows, turns


def propose(goal: str, history: list[dict]) -> tuple[list[dict], str, str]:
    """Returns (candidates, llm_mode, note). Probes are always included."""
    probes = _probe_rows()
    probe_keys = {
        (normalize_composition(p["composition"]), normalize_processing(p["processing"])) for p in probes
    }

    key = anthropic_key()
    if key:
        try:
            llm_rows, turns = _propose_anthropic(goal, history, key)
            kept: list[dict] = []
            seen = set(probe_keys)
            for row in llm_rows:
                row_key = (normalize_composition(row["composition"]), normalize_processing(row["processing"]))
                if row_key not in seen:  # skip anything the probes already cover
                    seen.add(row_key)
                    kept.append(row)
            if kept:
                note = (
                    f"Claude ({anthropic_model()}) made {turns} tool-calling turn(s); "
                    "all ratios came from bayesian_optimizer; boundary probes appended"
                )
                return _number(kept[:MAX_LLM_CANDIDATES] + probes), "anthropic", note
            fallback_note = "Claude made no usable optimizer calls; used mock plan"
        except Exception as exc:  # network, auth, or SDK errors fall back to the mock
            fallback_note = f"Anthropic call failed ({type(exc).__name__}); used mock plan"
    else:
        fallback_note = "No ANTHROPIC_API_KEY set; used deterministic mock orchestrator"

    control = _rows(bayesian_optimizer(*ALLOWED_CONTROL, n=1), origin="mock_control")
    return _number(probes + control), "mock", fallback_note
