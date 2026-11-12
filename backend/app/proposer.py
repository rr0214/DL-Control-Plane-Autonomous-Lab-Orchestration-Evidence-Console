"""Candidate proposal. Real LLM tool-calling when ANTHROPIC_API_KEY is set, mock plan otherwise.

Every tool call goes through the MCP gateway (mcp_server.gateway). In both modes:
- every composition ratio comes from propose_alloy_ratios (the model never writes stoichiometry)
- two boundary probes are always appended, so the Policy Kernel visibly blocks them:
    1. Hf candidate                    -> RESTRICTED_ELEMENT
    2. Run-088 exact repeat (Arc-Melt) -> DUPLICATE_CONDITION
- one demo Yellow control is always appended: a control route whose SEM scan is ambiguous,
  so the human-in-the-loop card appears on screen. This is a demo device, not a model choice.
"""
from __future__ import annotations

import json
from typing import Callable

from .chemistry import normalize_composition, normalize_processing
from .config import anthropic_key, anthropic_model
from .optimizer import TOOL_SCHEMA

MAX_LLM_CANDIDATES = 1

# (elements, processing) routes. Each probe is resolved to ratios by the propose tool.
BOUNDARY_PROBES = [
    (["Nb", "Ti", "Hf", "Al"], "Additive/Anneal"),  # restricted element
    (["Nb", "Ti", "Cr", "Al"], "Arc-Melt"),         # exact Run-088 composition + processing
]

# Same composition as the Run-088 probe on a new route: the gate allows it, and its telemetry is Yellow.
YELLOW_CONTROL = (["Nb", "Ti", "Cr", "Al"], "Additive/Anneal")

SYSTEM_PROMPT = (
    "You are the campaign planner for an autonomous materials lab. You never write "
    "stoichiometry yourself. To propose a composition you call the propose_alloy_ratios tool "
    "with an element set and a processing route, and you may only use the ratios it returns. "
    "Make one tool call. Explore a new composition: do not use the restricted element Hf and "
    "do not repeat a prior run. The policy team adds its own boundary and control checks, "
    "so do not try to include them. Keep any text reply to one sentence."
)

ToolCall = Callable[[str, dict], tuple[dict, str]]


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
    return [dict(row, candidate_id=f"C-{i}", source="propose_alloy_ratios") for i, row in enumerate(rows, 1)]


def _route_rows(call: ToolCall, elements: list[str], processing: str, origin: str, calls: list[dict]) -> list[dict]:
    output, transport = call("propose_alloy_ratios", {"elements": elements, "processing": processing, "n": 1})
    calls.append({"tool": "propose_alloy_ratios", "transport": transport, "args": {"elements": elements, "processing": processing}})
    return _rows(output, origin)


def _propose_anthropic(goal: str, history: list[dict], key: str, call: ToolCall, calls: list[dict]) -> tuple[list[dict], int]:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    prior = "\n".join(
        f"- {r['run_id']}: {r['composition']} via {r['processing']} -> {r['outcome']}" for r in history
    )
    messages = [
        {
            "role": "user",
            "content": f"Campaign goal: {goal}\nPrior runs:\n{prior}\n\nPropose one new candidate route now.",
        }
    ]
    rows: list[dict] = []
    turns = 0
    for _ in range(3):
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
            if use.name != "propose_alloy_ratios":
                output = {"error": f"unknown tool: {use.name}"}
            else:
                try:
                    output, transport = call("propose_alloy_ratios", dict(use.input))
                    calls.append({"tool": "propose_alloy_ratios", "transport": transport, "args": dict(use.input)})
                    rows.extend(_rows(output, origin="llm"))
                except (TypeError, ValueError, KeyError) as exc:
                    output = {"error": str(exc)}
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(output)})
        messages.append({"role": "user", "content": results})
    return rows, turns


def propose(goal: str, history: list[dict], call: ToolCall) -> tuple[list[dict], str, str, list[dict]]:
    """Returns (candidates, llm_mode, note, tool_calls). Controls are always included."""
    calls: list[dict] = []
    probes: list[dict] = []
    for elements, processing in BOUNDARY_PROBES:
        probes.extend(_route_rows(call, elements, processing, "boundary_probe", calls))
    control = _route_rows(call, *YELLOW_CONTROL, "yellow_control", calls)
    fixed = probes + control
    fixed_keys = {
        (normalize_composition(r["composition"]), normalize_processing(r["processing"])) for r in fixed
    }

    key = anthropic_key()
    if key:
        try:
            llm_rows, turns = _propose_anthropic(goal, history, key, call, calls)
            kept: list[dict] = []
            seen = set(fixed_keys)
            for row in llm_rows:
                row_key = (normalize_composition(row["composition"]), normalize_processing(row["processing"]))
                if row_key not in seen:  # drop anything the controls already cover
                    seen.add(row_key)
                    kept.append(row)
            if kept:
                note = (
                    f"Claude ({anthropic_model()}) made {turns} tool-calling turn(s); ratios came from "
                    "propose_alloy_ratios; boundary probes and Yellow control appended"
                )
                return _number(kept[:MAX_LLM_CANDIDATES] + fixed), "anthropic", note, calls
            fallback_note = "Claude made no usable tool calls; used mock plan"
        except Exception as exc:  # network, auth, or SDK errors fall back to the mock
            fallback_note = f"Anthropic call failed ({type(exc).__name__}); used mock plan"
    else:
        fallback_note = "No ANTHROPIC_API_KEY set; used deterministic mock orchestrator"

    return _number(fixed), "mock", fallback_note, calls
