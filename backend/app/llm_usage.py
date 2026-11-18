"""Every real LLM call goes through call(): it times the call, reads token counts, prices it, and
puts the result on a trace span and in a record that is saved with the plan.

PRICES ARE MANUALLY SET and must be verified against current pricing before anyone quotes a cost.
An unknown model gets cost None, never a guess.
"""
from __future__ import annotations

import functools
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from . import telemetry

# USD per million tokens: (input, output). Manually entered. VERIFY AGAINST CURRENT PRICING.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (3.00, 15.00),
    "claude-opus-5-5": (5.00, 25.00),
    "claude-haiku-5-5": (1.00, 5.00),
}
PRICE_NOTE = "Prices are set by hand in backend/app/llm_usage.py. Verify against current pricing before quoting a cost."


@functools.lru_cache(maxsize=1)
def git_commit() -> str:
    """Short commit of the running code, so a trace can be tied to the exact version. SDL_GIT_COMMIT overrides."""
    if os.getenv("SDL_GIT_COMMIT"):
        return os.environ["SDL_GIT_COMMIT"]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES_USD_PER_MTOK.get(model)
    if price is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 6)


def call(client: Any, *, agent: str, prompt_version: str, **kwargs: Any) -> tuple[Any, dict]:
    """client.messages.create(**kwargs) plus a usage record and a span. kwargs must include model."""
    model = kwargs["model"]
    with telemetry.span(f"llm.{agent}", kind="LLM", agent=agent, prompt_version=prompt_version, git_commit=git_commit()) as sp:
        started = time.perf_counter()
        response = client.messages.create(**kwargs)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cost = cost_usd(model, input_tokens, output_tokens)
        record = {
            "agent": agent,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "prompt_version": prompt_version,
            "git_commit": git_commit(),
        }
        telemetry.set_attrs(
            sp,
            {
                "llm.model_name": model,
                "llm.token_count.prompt": input_tokens,
                "llm.token_count.completion": output_tokens,
                "llm.token_count.total": input_tokens + output_tokens,
                "llm.cost_usd": cost,
                "llm.latency_ms": latency_ms,
            },
        )
    return response, record


def totals(records: list[dict]) -> dict:
    """Sum a plan's records. cost_usd is None when any call used a model with no price."""
    costs = [r["cost_usd"] for r in records]
    return {
        "calls": len(records),
        "input_tokens": sum(r["input_tokens"] for r in records),
        "output_tokens": sum(r["output_tokens"] for r in records),
        "cost_usd": None if (not records or any(c is None for c in costs)) else round(sum(costs), 6),
        "latency_ms": round(sum(r["latency_ms"] for r in records), 1),
        "models": sorted({r["model"] for r in records}),
    }
