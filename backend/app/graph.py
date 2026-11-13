"""The CampaignOrchestrator LangGraph: retrieve -> propose -> policy gate -> triage (HITL).

Tool use goes through the MCP gateway (mcp_server.gateway), so every tool call is
recorded with its transport (fastmcp or direct) in state.tool_calls.
"""
from __future__ import annotations

import functools
from dataclasses import asdict
from typing import Any, TypedDict

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import db, policy_kernel, presynthesis, proposer, telemetry, workcell
from .mcp_server import gateway

CAMPAIGN_ELEMENTS = ["Nb", "Ti", "Cr", "Al"]


class CampaignState(TypedDict, total=False):
    campaign_id: str
    goal: str
    scope: dict[str, Any]
    history: list[dict[str, Any]]
    literature: list[dict[str, Any]]
    llm_mode: str
    notes: list[str]
    tool_calls: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    verdicts: list[dict[str, Any]]
    approved: list[dict[str, Any]]
    triage: list[dict[str, Any]]


def traced_node(name: str):
    """Wrap a graph node in an OpenTelemetry span. A HITL interrupt is a pause, not an error."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(state: CampaignState):
            with telemetry.span(
                f"node.{name}", passthrough=(GraphBubbleUp,), campaign_id=state.get("campaign_id"), mcp_mode=gateway.mode
            ) as sp:
                try:
                    return fn(state)
                except GraphBubbleUp:
                    sp.set_attribute("paused_for_review", True)
                    raise

        return wrapper

    return deco


@traced_node("retrieve_context")
def retrieve_context(state: CampaignState) -> dict[str, Any]:
    conn = db.connect()
    try:
        campaign = db.get_campaign(conn, state["campaign_id"])
        history = db.get_runs(conn, state["campaign_id"])
    finally:
        conn.close()
    lit, transport = gateway.call(
        "search_calphad_literature", {"elements": CAMPAIGN_ELEMENTS, "topic": None, "limit": 3}
    )
    call = {"tool": "search_calphad_literature", "transport": transport, "args": {"elements": CAMPAIGN_ELEMENTS}}
    return {
        "goal": campaign["goal"],
        "scope": {"tenant": campaign["tenant"], "export_control": campaign["export_control"]},
        "history": history,
        "literature": lit["results"],
        "tool_calls": [*state.get("tool_calls", []), call],
        "notes": [f"Loaded {len(history)} prior runs and {len(lit['results'])} literature references"],
    }


@traced_node("propose_candidates")
def propose_candidates(state: CampaignState) -> dict[str, Any]:
    candidates, mode, note, calls = proposer.propose(state["goal"], state["history"], gateway.call)
    return {
        "candidates": candidates,
        "llm_mode": mode,
        "notes": [*state.get("notes", []), note],
        "tool_calls": [*state.get("tool_calls", []), *calls],
    }


@traced_node("policy_kernel")
def policy_kernel_node(state: CampaignState) -> dict[str, Any]:
    verdicts, approved, calls = [], [], []
    for cand in state["candidates"]:
        neg, transport = gateway.call(
            "check_negative_runs", {"composition": cand["composition"], "processing": cand["processing"]}
        )
        calls.append({"tool": "check_negative_runs", "transport": transport, "args": {"composition": cand["composition"]}})
        prior = [
            {
                "run_id": m["run_id"],
                "composition": cand["composition"],
                "processing": cand["processing"],
                "outcome": m["outcome"],
            }
            for m in neg["exact_matches"]
        ]
        with telemetry.span(
            "policy.check", campaign_id=state.get("campaign_id"), candidate_id=cand["candidate_id"]
        ) as psp:
            verdict = policy_kernel.check(cand, prior)
            psp.set_attribute("policy_status", "Allowed" if verdict.allowed else "Blocked")
            psp.set_attribute("policy_rule", verdict.rule)
        verdicts.append(asdict(verdict))
        if verdict.allowed:
            approved.append(cand)
    return {
        "verdicts": verdicts,
        "approved": approved,
        "tool_calls": [*state.get("tool_calls", []), *calls],
    }


@traced_node("triage_and_hitl")
def triage_and_hitl(state: CampaignState) -> dict[str, Any]:
    """Human review BEFORE synthesis, then scan triage for whatever was actually made.

    1. Every recipe the Policy Kernel allowed gets mock pre-synthesis risk signals.
    2. If the risk is high (borderline ductility margin), the graph pauses with interrupt() so a
       scientist can approve, revise, or reject the recipe. Nothing physical exists yet.
    3. Only approved (or low-risk) recipes are synthesized and scanned. Revised or rejected
       recipes are held: no sample, no scan.
    The checkpointer saves state while paused, so the review can happen hours or days later.
    """
    triage: list[dict[str, Any]] = []
    for cand in state.get("approved", []):
        risk = presynthesis.risk_signals(cand["composition"], cand["processing"])
        review_required = presynthesis.needs_review(risk)
        with telemetry.span(
            "presynthesis.review",
            campaign_id=state.get("campaign_id"),
            candidate_id=cand["candidate_id"],
            predicted_ductility_margin=risk["predicted_ductility_margin"],
            # Everything the scientist sees on the review card, so a trace can reconstruct the decision.
            predicted_elongation_pct=risk.get("predicted_elongation_pct"),
            baseline_elongation_pct=risk.get("baseline_elongation_pct"),
            min_elongation_pct=risk.get("min_elongation_pct"),
            ductility_label=risk.get("ductility_label"),
            baseline_run=risk.get("baseline_run"),
            phase_stability=risk.get("phase_stability"),
            furnace_blast_radius=risk["furnace_blast_radius"],
            review_required=review_required,
        ):
            pass
        record: dict[str, Any] = {
            "sample_id": f"S-{cand['candidate_id']}",
            "candidate_id": cand["candidate_id"],
            "composition": cand["composition"],
            "processing": cand["processing"],
            "status": None,
            "risk": risk,
            "telemetry": None,
            "decision": None,
            "intuition_note": "",
            "follow_up": None,
        }
        if review_required:
            # Pauses the graph BEFORE synthesis. The scan telemetry does not exist yet.
            reply = interrupt(
                {
                    "stage": "pre_synthesis",
                    "sample_id": record["sample_id"],
                    "candidate_id": cand["candidate_id"],
                    "status": "Yellow",
                    "composition": cand["composition"],
                    "processing": cand["processing"],
                    "risk": risk,
                    "decision": None,
                    "reason": presynthesis.review_reason(risk),
                    "options": ["approve", "revise", "reject"],
                }
            )
            record["decision"] = reply["decision"]
            record["intuition_note"] = reply.get("note", "")
            if record["decision"] != "approve":
                record["status"] = "Held"
                record["follow_up"] = "Not synthesized: held at pre-synthesis review."
                triage.append(record)
                continue

        # Synthesis is simulated. Scan data only exists for recipes that were actually made.
        telemetry_row = workcell.read_telemetry(cand["composition"], cand["processing"])
        status = workcell.classify(telemetry_row)
        with telemetry.span(
            "sample.triage",
            campaign_id=state.get("campaign_id"),
            candidate_id=cand["candidate_id"],
            cv_confidence=float(telemetry_row["sem_cv_confidence"]),
            triage_status=status,
        ):
            pass
        record["telemetry"] = telemetry_row
        record["status"] = status
        if record["decision"] is None:
            record["decision"] = {"Green": "auto_advance", "Red": "early_kill"}.get(status, "scan_flagged")
        if status != "Green":
            sem = telemetry_row["sem_cv_confidence"]
            record["follow_up"] = (
                f"Post-scan {status}: SEM confidence {sem:.2f}. Flagged for follow-up; it does not block the run."
            )
        triage.append(record)
    return {"triage": triage}


def build_graph(checkpointer):
    graph = StateGraph(CampaignState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("propose_candidates", propose_candidates)
    graph.add_node("policy_kernel", policy_kernel_node)
    graph.add_node("triage_and_hitl", triage_and_hitl)
    graph.add_edge(START, "retrieve_context")
    graph.add_edge("retrieve_context", "propose_candidates")
    graph.add_edge("propose_candidates", "policy_kernel")
    graph.add_edge("policy_kernel", "triage_and_hitl")
    graph.add_edge("triage_and_hitl", END)
    return graph.compile(checkpointer=checkpointer)
