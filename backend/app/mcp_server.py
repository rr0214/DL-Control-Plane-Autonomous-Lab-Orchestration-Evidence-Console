"""Core Platform tool contract, exposed as a FastMCP server.

Three tools are defined here. The graph reaches them through ToolGateway, which calls
them over an in-memory MCP session (real protocol, no subprocess). If the mcp package
is unavailable, or the session fails, the gateway calls the same Python functions
directly and reports the transport it used, so the UI can say which path ran.

Set SDL_MCP_MODE=direct to skip FastMCP entirely (used by the fast test path).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from . import db
from .chemistry import normalize_composition, normalize_processing
from .optimizer import bayesian_optimizer

log = logging.getLogger(__name__)
LITERATURE_PATH = Path(__file__).with_name("literature.json")


# ---- tool implementations (shared by FastMCP and the direct fallback) -----------------

def propose_alloy_ratios(elements: list[str], processing: str, n: int = 1) -> dict:
    """Propose numeric alloy compositions (percent per element, summing to 100) for an element set and processing route."""
    return bayesian_optimizer(elements, processing, n)


def check_negative_runs(composition: str, processing: str, campaign_id: str = "CAMP-014") -> dict:
    """Look up prior runs with the same composition and processing route, including failed ones."""
    conn = db.connect()
    try:
        runs = db.get_runs(conn, campaign_id)
    finally:
        conn.close()
    key = (normalize_composition(composition), normalize_processing(processing))
    exact = [
        {"run_id": r["run_id"], "outcome": r["outcome"], "note": r["note"]}
        for r in runs
        if (normalize_composition(r["composition"]), normalize_processing(r["processing"])) == key
    ]
    same_comp_other_route = [
        {"run_id": r["run_id"], "processing": r["processing"], "outcome": r["outcome"]}
        for r in runs
        if normalize_composition(r["composition"]) == key[0] and normalize_processing(r["processing"]) != key[1]
    ]
    return {
        "composition": composition,
        "processing": processing,
        "exact_matches": exact,
        "same_composition_other_routes": same_comp_other_route,
    }


def search_calphad_literature(elements: list[str] | None = None, topic: str | None = None, limit: int = 5) -> dict:
    """Search the curated CALPHAD and refractory-alloy literature list. Returns phase-stability and DOI citations."""
    items = json.loads(LITERATURE_PATH.read_text(encoding="utf-8"))
    wanted = set(elements or [])
    results = []
    for item in items:
        if topic and not any(topic.lower() in t.lower() for t in item["topics"]):
            continue
        if wanted and not (wanted & set(item["systems"])):
            continue
        results.append(dict(item, doi_url=f"https://doi.org/{item['doi']}"))
    return {
        "query": {"elements": sorted(wanted), "topic": topic},
        "results": results[: max(1, min(int(limit), 10))],
        "source": "Curated list. Titles, authors, and DOIs were checked against the paper text.",
    }


DIRECT_TOOLS = {
    "propose_alloy_ratios": propose_alloy_ratios,
    "check_negative_runs": check_negative_runs,
    "search_calphad_literature": search_calphad_literature,
}

# ---- FastMCP server -----------------------------------------------------------------------

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    _MCP_IMPORTED = True
except ImportError:  # pragma: no cover - exercised only when mcp is not installed
    _MCP_IMPORTED = False

server = None
if _MCP_IMPORTED:
    server = FastMCP("sdl-control-plane")
    server.tool()(propose_alloy_ratios)
    server.tool()(check_negative_runs)
    server.tool()(search_calphad_literature)


class ToolGateway:
    """Calls Core Platform tools over an in-memory MCP session, or directly as a fallback."""

    def __init__(self) -> None:
        requested = os.getenv("SDL_MCP_MODE", "auto").lower()
        self.mode = "direct" if (requested == "direct" or not _MCP_IMPORTED) else "fastmcp"

    def call(self, name: str, args: dict[str, Any]) -> tuple[dict, str]:
        """Returns (result, transport). transport is 'fastmcp' or 'direct'."""
        if name not in DIRECT_TOOLS:
            raise KeyError(f"Unknown tool {name}")
        if self.mode == "fastmcp":
            try:
                return asyncio.run(self._call_fastmcp(name, args)), "fastmcp"
            except Exception as exc:  # fall back rather than fail the run
                log.warning("FastMCP call to %s failed (%s); using direct fallback", name, exc)
        return DIRECT_TOOLS[name](**args), "direct"

    async def _call_fastmcp(self, name: str, args: dict[str, Any]) -> dict:
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
        if result.isError:
            raise RuntimeError(result.content[0].text if result.content else "tool error")
        return json.loads(result.content[0].text)


gateway = ToolGateway()
