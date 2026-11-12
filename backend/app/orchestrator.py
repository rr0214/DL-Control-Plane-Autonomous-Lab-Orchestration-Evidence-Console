"""Public entry point. Wraps the LangGraph so callers plan a batch, then review paused samples."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .config import checkpoint_path
from .graph import build_graph

VALID_DECISIONS = ("approve", "rescan", "kill")


class CampaignOrchestrator:
    def __init__(self, checkpoint_file: str | None = None):
        path = checkpoint_file or checkpoint_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self.graph = build_graph(SqliteSaver(self._conn))

    def plan(self, campaign_id: str, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        with self._lock:
            out = self.graph.invoke({"campaign_id": campaign_id}, config)
            return self._summarize(thread_id, config, out)

    def review(self, thread_id: str, decision: str, note: str = "") -> dict:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}")
        config = {"configurable": {"thread_id": thread_id}}
        with self._lock:
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
        }
