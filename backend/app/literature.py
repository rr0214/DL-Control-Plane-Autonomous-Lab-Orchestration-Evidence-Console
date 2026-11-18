"""Literature agent (loop step 2, an LLM).

Code retrieves the references first (the curated list, through the MCP gateway). Claude then reads
them and suggests directions. It may only cite references that were retrieved: code drops any
direction whose citations are not in the retrieved set. Without an API key, or if the call fails,
no directions are produced and the run says so (mock fallback = the plain lookup).
"""
from __future__ import annotations

import json
from typing import Callable

from . import llm_usage
from .config import agent_model, anthropic_key
from .targets import describe as describe_targets

PROMPT_VERSION = "literature-v1"
MAX_DIRECTIONS = 3

SYSTEM_PROMPT = (
    "You are the literature agent for an autonomous materials lab. You are given a campaign goal, "
    "customer targets and a numbered list of references. Suggest up to 3 research directions "
    "(element additions or processing routes worth trying) that the references support. "
    "Cite only reference ids from the list. Do not propose specific compositions or percentages. "
    "Reply with JSON only: {\"directions\": [{\"direction\": \"one sentence\", \"cited_ids\": [\"id\"]}]}"
)

ToolCall = Callable[[str, dict], tuple[dict, str]]


def _refs_text(refs: list[dict]) -> str:
    return "\n".join(f"- id={r['id']}: {r['title']} ({r['year']}). {r.get('note', '')}" for r in refs)


def parse_directions(text: str, refs: list[dict]) -> list[dict]:
    """Pull the JSON out of the reply and keep only directions whose citations were really retrieved."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        raw = json.loads(text[start : end + 1]).get("directions", [])
    except (ValueError, AttributeError):
        return []
    known = {r["id"]: r for r in refs}
    kept = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("direction"), str):
            continue
        cited = [i for i in item.get("cited_ids", []) if isinstance(i, str) and i in known]
        if cited:  # a direction with no valid citation is dropped
            kept.append({"direction": item["direction"].strip(), "cited_ids": cited})
    return kept[:MAX_DIRECTIONS]


def run(goal: str, targets: dict | None, elements: list[str], call: ToolCall) -> dict:
    """Returns {references, directions, mode, note, usage, tool_calls}. mode is 'anthropic' or 'mock'."""
    lit, transport = call("search_calphad_literature", {"elements": elements, "topic": None, "limit": 3})
    refs = lit["results"]
    out = {
        "references": refs,
        "directions": [],
        "mode": "mock",
        "usage": [],
        "tool_calls": [{"tool": "search_calphad_literature", "transport": transport, "args": {"elements": elements}}],
    }
    key = anthropic_key()
    if not key:
        out["note"] = f"No ANTHROPIC_API_KEY set; literature step was a plain lookup ({len(refs)} references, no directions)"
        return out
    model = agent_model("literature")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        response, record = llm_usage.call(
            client,
            agent="literature",
            prompt_version=PROMPT_VERSION,
            model=model,
            max_tokens=700,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Campaign goal: {goal}\n{describe_targets(targets)}\nReferences:\n{_refs_text(refs)}",
                }
            ],
        )
        out["usage"].append(record)
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        out["directions"] = parse_directions(text, refs)
        out["mode"] = "anthropic"
        out["note"] = (
            f"Claude ({model}) read {len(refs)} references and suggested {len(out['directions'])} direction(s); "
            "citations limited to retrieved references"
        )
    except Exception as exc:  # network, auth, or SDK errors fall back to the plain lookup
        out["note"] = f"Literature agent call failed ({type(exc).__name__}); used plain lookup"
    return out
