"""Public entry point. Wraps the LangGraph so callers plan a batch, then review paused samples."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from . import llm_usage, telemetry
from .config import checkpoint_path
from .graph import build_graph
from .mcp_server import gateway

VALID_DECISIONS = ("approve", "revise", "reject")


def pick_of(summary: dict) -> dict | None:
    """The optimizer's pick (the main path), or None when there was no search space or the run stopped."""
    return next((c for c in summary.get("candidates", []) if c.get("origin") == "optimizer"), None)


def pick_attributes(summary: dict) -> dict:
    """Span attributes that say what happened to the optimizer's pick, so a trace answers it at a glance."""
    pick = pick_of(summary)
    attrs: dict = {"target_check.feasible": (summary.get("target_check") or {}).get("feasible"),
                   "target_check.rule": (summary.get("target_check") or {}).get("rule") or "none",
                   "pick.composition": pick["composition"] + " via " + pick["processing"] if pick else "none"}
    if not pick:
        return attrs
    verdict = next((v for v in summary.get("verdicts", []) if v["candidate_id"] == pick["candidate_id"]), None)
    pending = summary.get("pending") or {}
    record = next((t for t in summary.get("triage", []) if t["candidate_id"] == pick["candidate_id"]), None)
    attrs.update({
        "pick.candidate_id": pick["candidate_id"],
        "pick.gate": ("allowed" if verdict["allowed"] else f"blocked {verdict['rule']}") if verdict else "not checked",
        "pick.reviewed": bool((record or {}).get("reviewed")) or pending.get("candidate_id") == pick["candidate_id"],
        "pick.decision": (record or {}).get("decision") or ("pending" if pending.get("candidate_id") == pick["candidate_id"] else "none"),
        "pick.status": (record or {}).get("status") or "none",
        "pick.made": bool(record and record.get("telemetry") is not None),
    })
    return attrs


class CampaignOrchestrator:
    def __init__(self, checkpoint_file: str | None = None):
        path = checkpoint_file or checkpoint_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self.graph = build_graph(SqliteSaver(self._conn))

    def plan(self, campaign_id: str, thread_id: str, targets: dict | None = None, forced_search_space: dict | None = None) -> dict:
        """forced_search_space is for test cases only: it skips the setup agent. Every later step runs as normal."""
        config = {"configurable": {"thread_id": thread_id}}
        with self._lock, telemetry.span("campaign.plan", kind="AGENT", campaign_id=campaign_id, thread_id=thread_id, mcp_mode=gateway.mode) as sp:
            state = {"campaign_id": campaign_id, "thread_id": thread_id, "targets": targets, "forced_search_space": forced_search_space}
            out = self.graph.invoke(state, config)
            summary = self._summarize(thread_id, config, out)
            telemetry.set_attrs(sp, pick_attributes(summary))
            sp.set_attribute("status", summary["status"])
            sp.set_attribute("git_commit", llm_usage.git_commit())
            sp.set_attribute("llm_calls", summary["llm_totals"]["calls"])
            if summary["llm_totals"]["cost_usd"] is not None:
                sp.set_attribute("llm_cost_usd", summary["llm_totals"]["cost_usd"])
            sp.set_attribute("targets", json.dumps(summary.get("targets") or {}))
            telemetry.record_io(
                sp,
                input=f"Plan the next batch for {campaign_id}. Targets: {json.dumps(targets or {})}",
                output=f"Status: {summary['status']}; setup_mode: {summary.get('setup_mode')}"
                + (f"\nStopped at the target check: {summary['target_check']['reason']}" if summary["status"] == "stopped" else "")
                + (f" ({summary['setup_error']})" if summary.get("setup_error") else "")
                + "\nCandidates:\n" + "\n".join(f"- {c['candidate_id']} {c['composition']} via {c['processing']}" for c in summary["candidates"])
                + "\nSafety gate: " + ", ".join(f"{v['candidate_id']} {'allowed' if v['allowed'] else 'blocked ' + str(v['rule'])}" for v in summary["verdicts"]),
            )
            sp.set_attribute("blocked_count", sum(1 for v in summary["verdicts"] if not v["allowed"]))
            return summary

    def review(self, thread_id: str, decision: str, note: str = "") -> dict:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}")
        config = {"configurable": {"thread_id": thread_id}}
        # scientist_override is True when the human did anything other than approve the Yellow sample.
        with self._lock, telemetry.span(
            "scientist.review",
            thread_id=thread_id,
            decision=decision,
            scientist_override=decision != "approve",
            review_note=(note or "").strip() or None,
        ) as rsp:
            waiting = self.pending(thread_id) or {}
            telemetry.set_attrs(rsp, {
                "review.sample_id": waiting.get("sample_id"),
                "review.candidate_id": waiting.get("candidate_id"),
                "review.is_pick": bool(waiting.get("is_pick")),
                "review.origin": waiting.get("origin"),
            })
            telemetry.record_io(
                rsp,
                input=f"Reviewing {waiting.get('sample_id')} ({'the optimizer pick' if waiting.get('is_pick') else waiting.get('origin') or 'unknown'}): "
                f"{waiting.get('composition')} via {waiting.get('processing')}\n"
                f"Scientist decision: {decision}\nScientist note: {(note or '').strip() or '(none)'}",
            )
            out = self.graph.invoke(Command(resume={"decision": decision, "note": note}), config)
            summary = self._summarize(thread_id, config, out)
            telemetry.set_attrs(rsp, pick_attributes(summary))
            telemetry.record_io(
                rsp,
                output="Samples after review:\n" + "\n".join(f"- {t['sample_id']}: {t['status']} ({t.get('decision')})" for t in summary["triage"]),
            )
            return summary

    def pending(self, thread_id: str) -> dict | None:
        """The review the thread is paused on right now, or None."""
        snapshot = self.graph.get_state({"configurable": {"thread_id": thread_id}})
        waiting = [i for task in snapshot.tasks for i in task.interrupts]
        return waiting[0].value if waiting else None

    def _summarize(self, thread_id: str, config: dict, out: dict) -> dict:
        pending = out.get("__interrupt__") or []
        values = self.graph.get_state(config).values
        check = values.get("target_check") or {}
        stopped = check.get("feasible") is False
        return {
            "status": "stopped" if stopped else "paused" if pending else "complete",
            "target_check": check or None,
            "thread_id": thread_id,
            "pending": pending[0].value if pending else None,
            "llm_mode": values.get("llm_mode"),
            "targets": values.get("targets"),
            "notes": values.get("notes", []),
            "candidates": values.get("candidates", []),
            "verdicts": values.get("verdicts", []),
            "approved": values.get("approved", []),
            "triage": values.get("triage", []),
            "literature": values.get("literature", []),
            "directions": values.get("directions", []),
            "literature_mode": values.get("literature_mode"),
            "setup_mode": values.get("setup_mode"),
            "setup_error": values.get("setup_error"),
            "search_space": values.get("search_space"),
            "llm_usage": values.get("llm_usage", []),
            "llm_totals": llm_usage.totals(values.get("llm_usage", [])),
            "tool_calls": values.get("tool_calls", []),
        }

    def forget_threads(self, thread_ids: list[str]) -> None:
        """Delete LangGraph checkpoints for the given threads only. Other data is untouched."""
        if not thread_ids:
            return
        marks = ",".join("?" for _ in thread_ids)
        with self._lock:
            for table in ("writes", "checkpoints"):
                try:
                    self._conn.execute(f"DELETE FROM {table} WHERE thread_id IN ({marks})", thread_ids)
                except sqlite3.OperationalError:  # table not created yet
                    pass
            self._conn.commit()
