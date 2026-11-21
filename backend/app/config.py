"""Runtime settings. Read at call time so tests can override environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Deterministic Policy Kernel rule: these elements are never allowed in a candidate.
RESTRICTED_ELEMENTS = frozenset({"Hf"})


def db_path() -> str:
    return os.getenv("SDL_DB_PATH", str(ROOT / "backend" / "data" / "sdl.db"))


def checkpoint_path() -> str:
    return os.getenv("SDL_CHECKPOINT_PATH", str(ROOT / "backend" / "data" / "checkpoints.sqlite"))


def anthropic_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def anthropic_model() -> str:
    """Kept for callers that predate per-agent settings. Prefer agent_model(agent)."""
    return os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL


# Per-agent model choice. Each agent reads its own setting, then ANTHROPIC_MODEL, then the default.
# Example: SDL_MODEL_SETUP=claude-opus-5-5 to try a bigger setup agent while the others stay on Sonnet.
DEFAULT_MODEL = "claude-sonnet-5-5"
AGENTS = ("setup", "diagnosis")


def agent_model(agent: str) -> str:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
    return os.getenv(f"SDL_MODEL_{agent.upper()}", "").strip() or os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL


def access_password() -> str:
    """Shared password for a hosted demo. Empty (the default) means no password, so local use is unchanged."""
    return os.getenv("SDL_ACCESS_PASSWORD", "").strip()


def daily_run_limit() -> int:
    """Most plan runs the API accepts per UTC day (SDL_DAILY_RUN_LIMIT). Unset or 0 means no limit, so local use is
    unchanged. A value that is not a whole number of 0 or more is an error, not a silent "no limit"."""
    raw = os.getenv("SDL_DAILY_RUN_LIMIT", "").strip()
    if not raw:
        return 0
    try:
        limit = int(raw)
    except ValueError:
        raise ValueError(f"SDL_DAILY_RUN_LIMIT must be a whole number, got {raw!r}") from None
    if limit < 0:
        raise ValueError(f"SDL_DAILY_RUN_LIMIT must be 0 or more, got {limit}")
    return limit


DEFAULT_ALLOWED_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def allowed_origins() -> list[str]:
    """Browser origins the API accepts (CORS). SDL_ALLOWED_ORIGINS is comma separated; unset means local use."""
    raw = os.getenv("SDL_ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_ALLOWED_ORIGINS)
