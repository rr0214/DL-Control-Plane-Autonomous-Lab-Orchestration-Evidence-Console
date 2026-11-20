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
        "tooling": "Targets stored on the campaign and passed to the setup agent. Default values are illustrative.",
        "type": "person",
        "mock": False,
        "status": "Built",
    },
    {
        "n": 2,
        "step": "Setup agent",
        "what": "One Claude call reads the references and the run history and sets the search space (allowed elements, a range for each, processing routes) plus directions that cite only retrieved references. It never writes ratios.",
        "tooling": "Code retrieves references (MCP tool search_calphad_literature); one forced tool call returns the search space and directions; code clamps the ranges and drops uncited directions. No API key: plain lookup, no search space, labeled mock.",
        "type": "LLM",
        "mock": False,
        "status": "Partly built",
    },
    {
        "n": 3,
        "step": "Optimizer",
        "what": "A numeric optimizer picks the exact ratios inside the search space. Only the optimizer writes percentages.",
        "tooling": "Fixed table standing in for a real optimizer (MCP tool propose_alloy_ratios, mock-optimizer-v1).",
        "type": "ML",
        "mock": True,
        "status": "Mock",
    },
    {
        "n": 4,
        "step": "Prediction model",
        "what": "A model scores each candidate recipe so the best new one leads the batch.",
        "tooling": "Fixed lookup standing in for a trained model (prediction_model.py, mock-prediction-v1).",
        "type": "ML",
        "mock": True,
        "status": "Mock",
    },
    {
        "n": 5,
        "step": "Safety gate",
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
        "step": "Make and measure",
        "what": "A robot makes the sample, then instruments measure composition, hardness and oxidation.",
        "tooling": "Simulated. No real synthesis. Measurements are mock values from hand-set formulas (measure.py), plus the earlier scan (SEM confidence, XRD match, crack flag).",
        "type": "code",
        "mock": True,
        "status": "Simulated",
    },
    {
        "n": 8,
        "step": "Measurement check",
        "what": "Fixed rules, a recipe vs measured composition check, and an anomaly flag against similar compositions.",
        "tooling": "check.py: readings sane, no restricted element, measured vs recipe composition, anomaly vs similar compositions. Real rules on simulated inputs; the scan rule still applies.",
        "type": "code",
        "mock": False,
        "status": "Built",
    },
    {
        "n": 9,
        "step": "Diagnosis agent",
        "what": "An LLM proposes re-measure or hold, with a reason. A code gate approves the action.",
        "tooling": "Claude reads one flagged sample's lineage and proposes re-measure or hold; a code gate decides. Actions are logged, not executed. No key: a rule-based stand-in.",
        "type": "LLM",
        "mock": False,
        "status": "Partly built",
    },
    {
        "n": 10,
        "step": "Release check",
        "what": "Results are compared to the customer targets, and a scientist signs off.",
        "tooling": "Results are compared with the customer targets (strength is an estimate from simulated data; temperature is not assessed until measured) and a scientist signs off. A Red sample cannot be released; an exception needs a written reason. A receipt is saved.",
        "type": "person",
        "mock": False,
        "status": "Built",
    },
]

# Span name -> (type, loop step number or None, mock). Names are the live OpenTelemetry names; the
# "node." prefix is stripped before lookup so the in-app span inspector names match too.
_SPAN_LABELS: dict[str, tuple[str, int | None, bool]] = {
    "campaign.plan": ("code", None, False),
    "setup_agent": ("LLM", 2, False),  # live span sets is_mock when there was no real LLM call
    "llm.setup": ("LLM", 2, False),
    "optimizer": ("ML", 3, True),
    "prediction_model": ("ML", 4, True),
    "prediction.score": ("ML", 4, True),
    "policy_kernel": ("code", 5, False),
    "policy.check": ("code", 5, False),
    "presynthesis.review": ("ML", 6, True),
    "triage_and_hitl": ("code", 6, False),
    "scientist.review": ("person", 6, False),
    "sample.triage": ("code", 8, True),
    "measure.sample": ("code", 7, True),
    "diagnose_flagged": ("LLM", 9, False),  # live span sets is_mock when the stand-in proposed
    "llm.diagnosis": ("LLM", 9, False),
    "action.gate": ("code", 9, False),
    "release.signoff": ("person", 10, False),
    "measurement.check": ("code", 8, False),
    "mcp.search_calphad_literature": ("code", 2, False),
    "mcp.propose_alloy_ratios": ("ML", 3, True),
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
