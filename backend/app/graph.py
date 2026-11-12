"""The CampaignOrchestrator LangGraph: retrieve -> propose -> policy gate -> triage (HITL)."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import db, policy_kernel, proposer, workcell


class CampaignState(TypedDict, total=False):
    campaign_id: str
    goal: str
    scope: dict[str, Any]
    history: list[dict[str, Any]]
    llm_mode: str
    notes: list[str]
    candidates: list[dict[str, Any]]
    verdicts: list[dict[str, Any]]
    approved: list[dict[str, Any]]
    triage: list[dict[str, Any]]


def retrieve_context(state: CampaignState) -> dict[str, Any]:
    conn = db.connect()
    try:
        campaign = db.get_campaign(conn, state["campaign_id"])
        history = db.get_runs(conn, state["campaign_id"])
    finally:
        conn.close()
    return {
        "goal": campaign["goal"],
        "scope": {"tenant": campaign["tenant"], "export_control": campaign["export_control"]},
        "history": history,
        "notes": [f"Loaded {len(history)} prior runs for {campaign['campaign_id']}"],
    }


def propose_candidates(state: CampaignState) -> dict[str, Any]:
    candidates, mode, note = proposer.propose(state["goal"], state["history"])
    return {"candidates": candidates, "llm_mode": mode, "notes": [*state.get("notes", []), note]}


def policy_kernel_node(state: CampaignState) -> dict[str, Any]:
    verdicts = policy_kernel.evaluate(state["candidates"], state["history"])
    approved = [c for c, v in zip(state["candidates"], verdicts) if v.allowed]
    return {"verdicts": [asdict(v) for v in verdicts], "approved": approved}


def triage_and_hitl(state: CampaignState) -> dict[str, Any]:
    triage: list[dict[str, Any]] = []
    for cand in state.get("approved", []):
        telemetry = workcell.read_telemetry(cand["composition"], cand["processing"])
        status = workcell.classify(telemetry)
        record: dict[str, Any] = {
            "sample_id": f"S-{cand['candidate_id']}",
            "candidate_id": cand["candidate_id"],
            "composition": cand["composition"],
            "processing": cand["processing"],
            "status": status,
            "telemetry": telemetry,
            "decision": None,
            "intuition_note": "",
        }
        if status == "Green":
            record["decision"] = "auto_advance"
        elif status == "Red":
            record["decision"] = "early_kill"
        else:
            # Pauses the graph. The checkpointer saves state until a scientist resumes it.
            reply = interrupt(
                {
                    "sample_id": record["sample_id"],
                    "status": "Yellow",
                    "composition": cand["composition"],
                    "processing": cand["processing"],
                    "reason": (
                        f"SEM scan CV confidence {telemetry['sem_cv_confidence']:.2f} "
                        "(sensor ambiguity, not composition novelty)"
                    ),
                    "options": ["approve", "rescan", "kill"],
                }
            )
            record["decision"] = reply["decision"]
            record["intuition_note"] = reply.get("note", "")
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
