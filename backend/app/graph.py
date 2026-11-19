"""The CampaignOrchestrator LangGraph: setup agent -> optimizer -> prediction model -> safety gate -> review (HITL) -> diagnosis.

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

from . import action_gate, check, config, db, diagnosis, history, measure, policy_kernel, prediction_model, presynthesis, proposer, setup_agent, telemetry, workcell
from .mcp_server import gateway

CAMPAIGN_ELEMENTS = ["Nb", "Ti", "Cr", "Al"]


class CampaignState(TypedDict, total=False):
    campaign_id: str
    thread_id: str
    goal: str
    targets: dict[str, Any]
    scope: dict[str, Any]
    history: list[dict[str, Any]]
    references: list[dict[str, Any]]
    literature: list[dict[str, Any]]
    directions: list[dict[str, Any]]
    literature_mode: str
    search_space: dict[str, Any] | None
    fixed_candidates: list[dict[str, Any]]
    space_candidates: list[dict[str, Any]]
    llm_usage: list[dict[str, Any]]
    llm_mode: str
    notes: list[str]
    tool_calls: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    verdicts: list[dict[str, Any]]
    approved: list[dict[str, Any]]
    triage: list[dict[str, Any]]
    diagnosis_mode: str


def traced_node(name: str):
    """Wrap a graph node in an OpenTelemetry span. A HITL interrupt is a pause, not an error."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(state: CampaignState):
            with telemetry.span(
                f"node.{name}", passthrough=(GraphBubbleUp,), campaign_id=state.get("campaign_id"), mcp_mode=gateway.mode
            ) as sp:
                try:
                    result = fn(state)
                    # A step that is an LLM step in the loop is a mock when no real LLM call happened.
                    if name == "diagnose_flagged":
                        sp.set_attribute("is_mock", result.get("diagnosis_mode") == "mock")
                    elif name == "setup_agent":
                        sp.set_attribute("is_mock", result.get("literature_mode") == "mock")
                    return result
                except GraphBubbleUp:
                    sp.set_attribute("paused_for_review", True)
                    raise

        return wrapper

    return deco


@traced_node("setup_agent")
def setup_agent_node(state: CampaignState) -> dict[str, Any]:
    conn = db.connect()
    try:
        campaign = db.get_campaign(conn, state["campaign_id"])
        # Seed runs plus the last few decided samples, with the scientist's decision and notes.
        prior = history.planner_history(conn, state["campaign_id"])
        references = history.measurement_references(conn, state["campaign_id"])
    finally:
        conn.close()
    # Targets passed in with the plan win; otherwise use the campaign's own.
    targets = state.get("targets") or campaign["targets"]
    out = setup_agent.run(campaign["goal"], targets, prior, CAMPAIGN_ELEMENTS, gateway.call)
    return {
        "goal": campaign["goal"],
        "targets": targets,
        "scope": {"tenant": campaign["tenant"], "export_control": campaign["export_control"]},
        "history": prior,
        "references": references,
        "literature": out["references"],
        "directions": out["directions"],
        "literature_mode": out["mode"],
        "search_space": out["space"],
        "llm_usage": [*state.get("llm_usage", []), *out["usage"]],
        "tool_calls": [*state.get("tool_calls", []), *out["tool_calls"]],
        "notes": [f"Loaded {len(prior)} prior runs and {len(out['references'])} literature references", out["note"]],
    }


@traced_node("optimizer")
def optimizer_node(state: CampaignState) -> dict[str, Any]:
    """Loop step 3 (mock). Exact ratios inside the search space, plus the fixed probes and control."""
    fixed, calls = proposer.fixed_rows(gateway.call)
    space_candidates: list[dict] = []
    space = state.get("search_space")
    if space:
        output, transport = gateway.call("propose_alloy_ratios", {"search_space": space, "n": 6})
        calls.append({"tool": "propose_alloy_ratios", "transport": transport, "args": {"search_space": True}})
        space_candidates = proposer.space_rows(output)
    return {
        "fixed_candidates": fixed,
        "space_candidates": space_candidates,
        "tool_calls": [*state.get("tool_calls", []), *calls],
    }


@traced_node("prediction_model")
def prediction_model_node(state: CampaignState) -> dict[str, Any]:
    """Loop step 4 (mock). Scores every candidate, then the best new recipe leads the batch."""
    fixed = prediction_model.score(state["fixed_candidates"])
    scored = prediction_model.score(state.get("space_candidates", []))
    chosen = proposer.pick(scored, fixed, state["history"]) if scored else []
    if chosen:
        pick = chosen[0]
        note = (
            f"Claude ({config.agent_model('setup')}) set the search space; the optimizer proposed {len(scored)} candidate(s) inside it "
            f"and the prediction model picked {pick['composition']} via {pick['processing']}; "
            "ratios came from propose_alloy_ratios; boundary probes and review control appended"
        )
    else:
        note = "No search space, so only the boundary probes and the review control run (mock plan)"
    return {
        "candidates": proposer.assemble(chosen, fixed),
        "llm_mode": "anthropic" if chosen else "mock",
        "notes": [*state.get("notes", []), note],
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
        # Loop step 7: make and measure (simulated). Step 8: the measurement check (plain code).
        with telemetry.span("measure.sample", campaign_id=state.get("campaign_id"), candidate_id=cand["candidate_id"]) as msp:
            measurements = measure.measure(cand["composition"], cand["processing"])
            msp.set_attribute("hardness_hv", measurements["hardness_hv"])
            msp.set_attribute("oxidation_mg_cm2", measurements["oxidation_mg_cm2"])
        with telemetry.span("measurement.check", campaign_id=state.get("campaign_id"), candidate_id=cand["candidate_id"]) as csp:
            result = check.run_checks(cand["composition"], measurements, state.get("references", []), record["sample_id"])
            csp.set_attribute("flags", ",".join(result["flags"]) or "none")
            csp.set_attribute("severity", result["severity"] or "none")
            csp.set_attribute("similar_count", len(result["similar"]))
        # The check can only make a sample's status worse, never better.
        rank = {"Green": 0, "Yellow": 1, "Red": 2}
        if result["severity"] and rank[result["severity"]] > rank[status]:
            status = result["severity"]
        record["telemetry"] = telemetry_row
        record["measurements"] = measurements
        record["measurement_check"] = result
        record["status"] = status
        if record["decision"] is None:
            record["decision"] = {"Green": "auto_advance", "Red": "early_kill"}.get(status, "scan_flagged")
        if status != "Green":
            sem = telemetry_row["sem_cv_confidence"]
            why = f"SEM confidence {sem:.2f}"
            if result["flags"]:
                why += f"; measurement check flagged {', '.join(result['flags'])}"
            record["follow_up"] = f"Post-scan {status}: {why}. Flagged for follow-up; it does not block the run."
        triage.append(record)
    return {"triage": triage}


@traced_node("diagnose_flagged")
def diagnose_flagged(state: CampaignState) -> dict[str, Any]:
    """Loop step 9. For each sample that was made and came out Yellow or Red, the diagnosis agent proposes an
    action and the action gate decides. Nothing is executed; the result is logged and shown."""
    triage = [dict(r) for r in state.get("triage", [])]
    usage: list[dict[str, Any]] = []
    notes: list[str] = []
    modes: list[str] = []
    conn = db.connect()
    try:
        for rec in triage:
            if rec.get("telemetry") is None or rec.get("status") not in ("Yellow", "Red") or rec.get("diagnosis"):
                continue
            result = diagnosis.propose(rec, state.get("references", []))
            usage.extend(result["usage"])
            modes.append(result["mode"])
            prior = db.count_remeasures(conn, state.get("thread_id", ""), rec["sample_id"])
            with telemetry.span("action.gate", campaign_id=state.get("campaign_id"), sample_id=rec["sample_id"]) as gsp:
                verdict = action_gate.gate(result["proposal"], rec, prior)
                gsp.set_attribute("allowed", verdict["allowed"])
                gsp.set_attribute("final_action", verdict["final_action"])
                gsp.set_attribute("rule", verdict["rule"] or "none")
            rec["diagnosis"] = {"mode": result["mode"], "gate": verdict, "executed": False}
            line = f"Diagnosis ({'Claude' if result['mode'] == 'anthropic' else 'mock'}): {verdict['final_action']}"
            if verdict["proposal"].get("cause") in action_gate.CAUSES:
                line += f", likely {verdict['proposal']['cause']}"
            if not verdict["allowed"]:
                line += f" (gate overrode the proposal: {verdict['rule']})"
            rec["follow_up"] = f"{rec.get('follow_up') or ''} {line}. Logged, not executed.".strip()
            notes.append(f"{rec['sample_id']}: {result['note']}")
    finally:
        conn.close()
    if not modes:
        return {}
    return {
        "triage": triage,
        "diagnosis_mode": "anthropic" if "anthropic" in modes else "mock",
        "llm_usage": [*state.get("llm_usage", []), *usage],
        "notes": [*state.get("notes", []), *notes],
    }


def build_graph(checkpointer):
    graph = StateGraph(CampaignState)
    graph.add_node("setup_agent", setup_agent_node)
    graph.add_node("optimizer", optimizer_node)
    graph.add_node("prediction_model", prediction_model_node)
    graph.add_node("policy_kernel", policy_kernel_node)
    graph.add_node("triage_and_hitl", triage_and_hitl)
    graph.add_node("diagnose_flagged", diagnose_flagged)
    graph.add_edge(START, "setup_agent")
    graph.add_edge("setup_agent", "optimizer")
    graph.add_edge("optimizer", "prediction_model")
    graph.add_edge("prediction_model", "policy_kernel")
    graph.add_edge("policy_kernel", "triage_and_hitl")
    graph.add_edge("triage_and_hitl", "diagnose_flagged")
    graph.add_edge("diagnose_flagged", END)
    return graph.compile(checkpointer=checkpointer)
