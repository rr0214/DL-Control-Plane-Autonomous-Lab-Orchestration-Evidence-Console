"""Public entry point. Wraps the LangGraph so callers plan a batch, then review paused samples."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from . import telemetry
from .config import checkpoint_path
from .graph import build_graph
from .mcp_server import gateway

VALID_DECISIONS = ("approve", "revise", "reject")


class CampaignOrchestrator:
    def __init__(self, checkpoint_file: str | None = None):
        path = checkpoint_file or checkpoint_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self.graph = build_graph(SqliteSaver(self._conn))

    def plan(self, campaign_id: str, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        with self._lock, telemetry.span("campaign.plan", campaign_id=campaign_id, thread_id=thread_id, mcp_mode=gateway.mode) as sp:
            out = self.graph.invoke({"campaign_id": campaign_id}, config)
            summary = self._summarize(thread_id, config, out)
            sp.set_attribute("status", summary["status"])
            sp.set_attribute("blocked_count", sum(1 for v in summary["verdicts"] if not v["allowed"]))
            return summary

    def review(self, thread_id: str, decision: str, note: str = "") -> dict:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}")
        config = {"configurable": {"thread_id": thread_id}}
        # scientist_override is True when the human did anything other than approve the Yellow sample.
        with self._lock, telemetry.span(
            "scientist.review", thread_id=thread_id, decision=decision, scientist_override=decision != "approve"
        ):
            out = self.graph.invoke(Command(resume={"decision": decision, "note": note}), config)
            return self._summarize(thread_id, config, out)

    def _summarize(self, thread_id: str, config: dict, out: dict) -> dict:
        pending = out.get("__interrupt__") or []
        values = self.graph.get_state(config).values
        return {
            "status": "paused" if pending else "complete",
            "thread_id": thread_id,
            "pending": pending[0].value if pending else None,
            "llm_mode": values.get("llm_mode"),
            "notes": values.get("notes", []),
            "candidates": values.get("candidates", []),
            "verdicts": values.get("verdicts", []),
            "approved": values.get("approved", []),
            "triage": values.get("triage", []),
            "literature": values.get("literature", []),
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
