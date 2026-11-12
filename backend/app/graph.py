"""The CampaignOrchestrator LangGraph: retrieve -> propose -> policy gate -> triage (HITL).

Tool use goes through the MCP gateway (mcp_server.gateway), so every tool call is
recorded with its transport (fastmcp or direct) in state.tool_calls.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import db, policy_kernel, proposer, workcell
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


def propose_candidates(state: CampaignState) -> dict[str, Any]:
    candidates, mode, note, calls = proposer.propose(state["goal"], state["history"], gateway.call)
    return {
        "candidates": candidates,
        "llm_mode": mode,
        "notes": [*state.get("notes", []), note],
        "tool_calls": [*state.get("tool_calls", []), *calls],
    }


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
        verdict = policy_kernel.check(cand, prior)
        verdicts.append(asdict(verdict))
        if verdict.allowed:
            approved.append(cand)
    return {
        "verdicts": verdicts,
        "approved": approved,
        "tool_calls": [*state.get("tool_calls", []), *calls],
    }


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
                    "candidate_id": cand["candidate_id"],
                    "status": "Yellow",
                    "composition": cand["composition"],
                    "processing": cand["processing"],
                    "telemetry": telemetry,
                    "decision": None,
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
