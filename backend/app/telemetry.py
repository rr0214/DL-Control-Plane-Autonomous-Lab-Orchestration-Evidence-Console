"""Live OpenTelemetry tracing to Arize Phoenix, with graceful degradation.

Rules:
- SDL_TRACING=off disables tracing entirely (the test suite sets this).
- If Phoenix is not listening on PHOENIX_COLLECTOR_ENDPOINT, tracing is skipped and the
  app runs normally.
- When no tracer provider is registered, the OpenTelemetry API hands back no-op spans, so
  the helpers below are always safe to call.

Live runs go to the Phoenix project `sdl-control-plane` (override with SDL_PHOENIX_PROJECT).
Curated historical examples live in a separate project, `sdl-control-plane-seed`
(see seed_phoenix.py).
"""
from __future__ import annotations

import logging
import os
import socket
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

log = logging.getLogger(__name__)

TRACER_NAME = "sdl-control-plane"
DEFAULT_ENDPOINT = "http://localhost:6006"
LIVE_PROJECT = "sdl-control-plane"
PHOENIX_UI_URL = "http://localhost:6006"

_state = {"enabled": False}


def endpoint() -> str:
    return os.getenv("PHOENIX_COLLECTOR_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def live_project() -> str:
    return os.getenv("SDL_PHOENIX_PROJECT", LIVE_PROJECT)


def tracing_requested() -> bool:
    return os.getenv("SDL_TRACING", "on").lower() != "off"


def is_enabled() -> bool:
    return _state["enabled"]


def phoenix_reachable(url: str | None = None, timeout: float = 0.3) -> bool:
    """Cheap TCP check so startup never waits on a Phoenix that is not running."""
    parsed = urlparse(url or endpoint())
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def init_tracing() -> bool:
    """Register Phoenix tracing for the live project. Returns True if tracing is active."""
    if _state["enabled"]:
        return True
    if not tracing_requested():
        return False
    url = endpoint()
    if not phoenix_reachable(url):
        log.info("Phoenix not reachable at %s; tracing is off", url)
        return False
    try:
        from phoenix.otel import register

        register(
            project_name=live_project(),
            endpoint=f"{url}/v1/traces",
            batch=True,  # async export: the UI never waits on Phoenix
            auto_instrument=True,
            set_global_tracer_provider=True,
            verbose=False,
        )
    except Exception as exc:  # never let observability break the app
        log.warning("Phoenix tracing failed to start (%s); continuing without it", exc)
        return False
    _state["enabled"] = True
    log.info("Phoenix tracing on: project=%s endpoint=%s", live_project(), url)
    return True


def set_attrs(sp: trace.Span, attrs: dict[str, Any]) -> None:
    for key, value in attrs.items():
        if value is not None:
            sp.set_attribute(key, value)


@contextmanager
def span(name: str, passthrough: tuple[type[BaseException], ...] = (), **attrs: Any) -> Iterator[trace.Span]:
    """Open a span. Exceptions in `passthrough` (for example a LangGraph interrupt) are re-raised
    without marking the span as an error."""
    with trace.get_tracer(TRACER_NAME).start_as_current_span(name, record_exception=False, set_status_on_exception=False) as sp:
        set_attrs(sp, attrs)
        try:
            yield sp
        except passthrough:
            raise
        except Exception as exc:
            sp.record_exception(exc)
            sp.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
