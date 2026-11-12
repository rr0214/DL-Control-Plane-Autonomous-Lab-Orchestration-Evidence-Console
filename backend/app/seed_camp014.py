"""Seeded CAMP-014 governance data, evidence receipts, and OpenTelemetry-shaped span trees.

Everything here is simulated for the demo. Span timings are illustrative, not measured.
"""
from __future__ import annotations

import hashlib
import json

RBAC = {
    "tenant": "SDL-Internal",
    "export_control": "ITAR",
    "roles": [
        {"role": "Scientist (PI)", "permissions": ["approve", "rescan", "kill", "view_evidence"]},
        {"role": "Operator", "permissions": ["rescan", "view_evidence"]},
        {"role": "Policy Owner", "permissions": ["view_evidence", "edit_policy"]},
        {"role": "Auditor", "permissions": ["view_evidence", "export_receipts"]},
    ],
    "decision_permissions": {"approve": "approve", "rescan": "rescan", "kill": "kill"},
    "principle": "Agents propose, humans decide at HITL gates, and no role can override the Policy Kernel.",
}


def make_receipt(record: dict) -> dict:
    payload = {k: record.get(k) for k in ("sample_id", "composition", "processing", "status", "decision")}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {
        "receipt_id": f"RCPT-{digest[:12]}",
        "content_sha256": digest,
        "instrument": record.get("instrument", "SEM-02"),
        "recorded_at": record["recorded_at"],
        "signed_by": "workcell-gateway",
    }


_SEED_RECORDS = [
    {
        "sample_id": "S-RUN-071",
        "composition": "Nb40-Ti30-Cr20-Al10",
        "processing": "Arc-Melt",
        "status": "Green",
        "decision": "auto_advance",
        "intuition_note": "",
        "telemetry": {"sem_cv_confidence": 0.95, "xrd_phase_match": 0.96, "crack_detected": False},
        "recorded_at": "2026-11-02T10:14:00-05:00",
    },
    {
        "sample_id": "S-RUN-088",
        "composition": "Nb50-Ti20-Cr15-Al15",
        "processing": "Arc-Melt",
        "status": "Red",
        "decision": "early_kill",
        "intuition_note": "Cracked during cooldown",
        "telemetry": {"sem_cv_confidence": 0.93, "xrd_phase_match": 0.91, "crack_detected": True},
        "recorded_at": "2026-11-04T16:40:00-05:00",
    },
]

SEED_SAMPLES = [dict(rec, receipt=make_receipt(rec)) for rec in _SEED_RECORDS]


def _span_id(trace_id: str, name: str, index: int = 0) -> str:
    return hashlib.sha256(f"{trace_id}:{name}:{index}".encode()).hexdigest()[:16]


def build_trace(
    thread_id: str,
    llm_mode: str,
    candidates: list[dict],
    verdicts: list[dict],
    triage: list[dict],
    tool_calls: list[dict] | None = None,
) -> dict:
    """OpenTelemetry-shaped span tree for one plan run. Timings are simulated."""
    trace_id = hashlib.sha256(thread_id.encode()).hexdigest()[:32]
    spans: list[dict] = []
    cursor = 0.0

    def add(name: str, parent: str | None, duration: float, attributes: dict, index: int = 0) -> str:
        nonlocal cursor
        sid = _span_id(trace_id, name, index)
        spans.append(
            {
                "span_id": sid,
                "parent_span_id": parent,
                "name": name,
                "start_ms": round(cursor, 1),
                "duration_ms": round(duration, 1),
                "attributes": attributes,
            }
        )
        return sid

    root = add("campaign.plan", None, 0, {"thread_id": thread_id, "llm.mode": llm_mode, "simulated": True})
    cursor = 0.0
    retrieve = add("retrieve_context", root, 12.0, {"db.system": "sqlite"})
    cursor += 12.0
    propose_ms = 850.0 if llm_mode == "anthropic" else 4.0
    propose = add("propose_candidates", root, propose_ms, {"llm.mode": llm_mode})
    for i, cand in enumerate(candidates, 1):
        add(
            "bayesian_optimizer",
            propose,
            2.0,
            {"tool.name": "bayesian_optimizer", "candidate_id": cand["candidate_id"], "origin": cand.get("origin")},
            index=i,
        )
    cursor += propose_ms

    gate = add("policy_kernel", root, sum(v["latency_ms"] for v in verdicts), {
        "policy.checked": len(verdicts),
        "policy.blocked": sum(1 for v in verdicts if not v["allowed"]),
    })
    for i, v in enumerate(verdicts, 1):
        add(
            "policy.check",
            gate,
            v["latency_ms"],
            {
                "candidate_id": v["candidate_id"],
                "allowed": v["allowed"],
                "rule": v["rule"] or "none",
            },
            index=i,
        )

    for i, call in enumerate(tool_calls or [], 1):
        add(
            f"mcp.{call['tool']}",
            root,
            1.5,
            {"mcp.transport": call["transport"], "tool.name": call["tool"], "simulated": True},
            index=100 + i,
        )

    triage_span = add("triage_and_hitl", root, 0.0, {"samples": len(triage)})
    for i, t in enumerate(triage, 1):
        add(
            "sample.triage",
            triage_span,
            0.0,
            {"sample_id": t["sample_id"], "status": t["status"], "decision": t.get("decision") or "pending"},
            index=i,
        )

    return {"trace_id": trace_id, "simulated": True, "spans": spans}


_SEED_CANDIDATES = [
    {"candidate_id": "C-1", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "origin": "boundary_probe"},
    {"candidate_id": "C-2", "composition": "Nb40-Ti25-Hf15-Al20", "processing": "Additive/Anneal", "origin": "boundary_probe"},
    {"candidate_id": "C-3", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Additive/Anneal", "origin": "mock_control"},
]
_SEED_VERDICTS = [
    {"candidate_id": "C-1", "allowed": False, "rule": "DUPLICATE_CONDITION", "latency_ms": 0.4},
    {"candidate_id": "C-2", "allowed": False, "rule": "RESTRICTED_ELEMENT", "latency_ms": 0.2},
    {"candidate_id": "C-3", "allowed": True, "rule": None, "latency_ms": 0.3},
]
SEED_TRACE = build_trace("seed-CAMP-014", "mock", _SEED_CANDIDATES, _SEED_VERDICTS, [])
