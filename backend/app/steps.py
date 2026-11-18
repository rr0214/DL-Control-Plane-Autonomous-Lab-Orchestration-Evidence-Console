"""The target loop, one row per step, and the label every span carries.

Each step is one of four types:
  LLM     a language model decides or writes
  ML      a numeric or learned model scores or optimizes
  code    plain deterministic code
  person  a human decides

`mock` marks a stand-in with demo values. `status` says how much of the step exists today.
Keep this file honest: when a step is built for real, change its status here and nothing else
(the API, the Architecture tab and the span labels all read from it).
"""
from __future__ import annotations

STEP_TYPES = ("LLM", "ML", "code", "person")
STATUSES = ("Built", "Mock", "Simulated", "Partly built", "Planned")

LOOP: list[dict] = [
    {
        "n": 1,
        "step": "Customer targets in",
        "what": "The customer sets target properties: high temperature performance, strength, reduced hafnium.",
        "tooling": "Targets stored on the campaign and passed to the planner. Default values are illustrative.",
        "type": "person",
        "mock": False,
        "status": "Built",
    },
    {
        "n": 2,
        "step": "Literature suggests directions",
        "what": "A literature agent reads references and suggests directions.",
        "tooling": "Code retrieves references (MCP tool search_calphad_literature); Claude suggests directions and may cite only those. No API key: plain lookup, no directions.",
        "type": "LLM",
        "mock": False,
        "status": "Partly built",
    },
    {
        "n": 3,
        "step": "Planner proposes recipes",
        "what": "The LLM picks element sets and routes. It never writes ratios.",
        "tooling": "Claude via tool calling when an API key is set. Otherwise a fixed mock plan.",
        "type": "LLM",
        "mock": False,
        "status": "Partly built",
    },
    {
        "n": 4,
        "step": "Optimizer picks exact ratios",
        "what": "A numeric optimizer sets the percentages and which candidates to test.",
        "tooling": "Fixed table standing in for a surrogate model (MCP tool propose_alloy_ratios).",
        "type": "ML",
        "mock": True,
        "status": "Mock",
    },
    {
        "n": 5,
        "step": "Safety check",
        "what": "Plain code blocks restricted elements and repeats of failed runs.",
        "tooling": "Policy Kernel (Python), MCP tool check_negative_runs.",
        "type": "code",
        "mock": False,
        "status": "Built",
    },
    {
        "n": 6,
        "step": "Scientist reviews risky plans",
        "what": "A scientist approves, revises or rejects a risky recipe before anything is made.",
        "tooling": "LangGraph interrupt() with SQLite checkpoints, role checks, SHA-256 receipts. Risk signals are a mock lookup.",
        "type": "person",
        "mock": False,
        "status": "Built",
    },
    {
        "n": 7,
        "step": "Make the sample",
        "what": "A robot makes the sample.",
        "tooling": "Simulated. No real synthesis.",
        "type": "code",
        "mock": True,
        "status": "Simulated",
    },
    {
        "n": 8,
        "step": "Measure properties",
        "what": "Instruments measure composition, hardness and oxidation.",
        "tooling": "Today only a simulated scan (SEM confidence, XRD match, crack flag). Property measurements are not built yet.",
        "type": "code",
        "mock": True,
        "status": "Partly built",
    },
    {
        "n": 9,
        "step": "Measurement check",
        "what": "Fixed rules, a recipe vs measured composition check, and an anomaly flag against similar compositions.",
        "tooling": "Today only the scan threshold rule (SEM confidence under 0.8 is Yellow).",
        "type": "code",
        "mock": False,
        "status": "Partly built",
    },
    {
        "n": 10,
        "step": "Diagnosis agent",
        "what": "An LLM proposes re-measure or hold, with a reason. A code gate approves the action.",
        "tooling": "Not built yet.",
        "type": "LLM",
        "mock": False,
        "status": "Planned",
    },
    {
        "n": 11,
        "step": "Release check",
        "what": "Results are compared to the customer targets, and a scientist signs off.",
        "tooling": "Not built yet.",
        "type": "person",
        "mock": False,
        "status": "Planned",
    },
]

# Span name -> (type, loop step number or None, mock). Names are the live OpenTelemetry names; the
# "node." prefix is stripped before lookup so the in-app span inspector names match too.
_SPAN_LABELS: dict[str, tuple[str, int | None, bool]] = {
    "campaign.plan": ("code", None, False),
    "retrieve_context": ("LLM", 2, False),  # live span sets is_mock when there was no real LLM call
    "propose_candidates": ("LLM", 3, False),  # live span also sets is_mock when the plan came from the mock
    "llm.literature": ("LLM", 2, False),
    "llm.planner": ("LLM", 3, False),
    "bayesian_optimizer": ("ML", 4, True),
    "policy_kernel": ("code", 5, False),
    "policy.check": ("code", 5, False),
    "presynthesis.review": ("ML", 6, True),
    "triage_and_hitl": ("code", 6, False),
    "scientist.review": ("person", 6, False),
    "sample.triage": ("code", 9, True),
    "mcp.search_calphad_literature": ("code", 2, False),
    "mcp.propose_alloy_ratios": ("ML", 4, True),
    "mcp.check_negative_runs": ("code", 5, False),
}


def span_labels(name: str) -> dict:
    """Attributes to put on a span so every trace row says which kind of step it is."""
    key = name[len("node."):] if name.startswith("node.") else name
    found = _SPAN_LABELS.get(key)
    if found is None:
        return {}
    step_type, step_n, mock = found
    labels: dict = {"step_type": step_type, "is_mock": mock}
    if step_n is not None:
        labels["step_n"] = step_n
    return labels


def loop() -> list[dict]:
    return [dict(s) for s in LOOP]
