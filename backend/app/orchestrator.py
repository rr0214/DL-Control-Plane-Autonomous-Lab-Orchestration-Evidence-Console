"""Public entry point. Wraps the LangGraph so callers plan a batch, then review paused samples."""
from __future__ import annotations

import sqlite3
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
        self.graph = build_graph(SqliteSaver(self._conn))

    def plan(self, campaign_id: str, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        out = self.graph.invoke({"campaign_id": campaign_id}, config)
        return self._summarize(thread_id, out)

    def review(self, thread_id: str, decision: str, note: str = "") -> dict:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}")
        config = {"configurable": {"thread_id": thread_id}}
        out = self.graph.invoke(Command(resume={"decision": decision, "note": note}), config)
        return self._summarize(thread_id, out)

    def _summarize(self, thread_id: str, out: dict) -> dict:
        pending = out.get("__interrupt__") or []
        if pending:
            return {"status": "paused", "thread_id": thread_id, "pending": pending[0].value}
        return {
            "status": "complete",
            "thread_id": thread_id,
            "llm_mode": out["llm_mode"],
            "notes": out["notes"],
            "candidates": out["candidates"],
            "verdicts": out["verdicts"],
            "triage": out["triage"],
        }
