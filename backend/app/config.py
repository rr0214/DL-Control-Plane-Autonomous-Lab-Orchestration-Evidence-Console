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
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
