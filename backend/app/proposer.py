"""Candidate proposal. Real LLM tool-calling when ANTHROPIC_API_KEY is set, mock plan otherwise.

In both modes, every composition ratio comes from bayesian_optimizer. The model
chooses element sets and processing routes; it never writes stoichiometry.
"""
from __future__ import annotations

import json

from .config import anthropic_key, anthropic_model
from .optimizer import ALLOWED_PROCESSING, TOOL_SCHEMA, bayesian_optimizer

MAX_CANDIDATES = 3

# Used when no key is set. Each route hits one policy outcome so the gate is visible in the UI.
MOCK_PLAN = [
    (["Nb", "Ti", "Cr", "Al"], "Arc-Melt"),         # repeats Run-088 exactly -> DUPLICATE_CONDITION
    (["Nb", "Ti", "Hf", "Al"], "Additive/Anneal"),  # contains Hf -> RESTRICTED_ELEMENT
    (["Nb", "Ti", "Cr", "Al"], "Additive/Anneal"),  # same composition, new route -> allowed
]

SYSTEM_PROMPT = (
    "You are the campaign planner for an autonomous materials lab. You never write "
    "stoichiometry yourself. To propose a composition you call the bayesian_optimizer tool "
    "with an element set and a processing route, and you may only use the ratios it returns. "
    "Make three tool calls in total. One call must include the restricted element Hf. "
    "One call must repeat a prior run's composition with its processing route, so the "
    "policy gate can be checked. Keep any text reply to one sentence."
)


def _rows(output: dict) -> list[dict]:
    return [
        {
            "composition": c["composition"],
            "processing": output["processing"],
            "expected_improvement": c["expected_improvement"],
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


def _propose_anthropic(goal: str, history: list[dict], key: str) -> tuple[list[dict], int]:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    prior = "\n".join(
        f"- {r['run_id']}: {r['composition']} via {r['processing']} -> {r['outcome']}" for r in history
    )
    messages = [
        {
            "role": "user",
            "content": f"Campaign goal: {goal}\nPrior runs:\n{prior}\n\nPropose three candidate routes now.",
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
            rows.extend(_rows(output))
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": json.dumps(output)})
        messages.append({"role": "user", "content": results})
    return rows, turns


def propose(goal: str, history: list[dict]) -> tuple[list[dict], str, str]:
    """Returns (candidates, llm_mode, note)."""
    key = anthropic_key()
    if key:
        try:
            rows, turns = _propose_anthropic(goal, history, key)
            if rows:
                note = (
                    f"Claude ({anthropic_model()}) made {turns} tool-calling turn(s); "
                    "all ratios came from bayesian_optimizer"
                )
                return _number(rows[:MAX_CANDIDATES]), "anthropic", note
            fallback_note = "Claude made no optimizer calls; used mock plan"
        except Exception as exc:  # network, auth, or SDK errors fall back to the mock
            fallback_note = f"Anthropic call failed ({type(exc).__name__}); used mock plan"
    else:
        fallback_note = "No ANTHROPIC_API_KEY set; used deterministic mock orchestrator"

    rows: list[dict] = []
    for elements, processing in MOCK_PLAN:
        rows.extend(_rows(bayesian_optimizer(elements, processing, n=1)))
    return _number(rows[:MAX_CANDIDATES]), "mock", fallback_note
