"""Deploy settings: CORS origins from SDL_ALLOWED_ORIGINS, with localhost when unset. No network."""
from fastapi.testclient import TestClient

from app import config
from app.api import create_app
from app.orchestrator import CampaignOrchestrator


def test_allowed_origins_default_to_localhost(monkeypatch):
    monkeypatch.delenv("SDL_ALLOWED_ORIGINS", raising=False)
    assert config.allowed_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_allowed_origins_are_comma_separated_and_trimmed(monkeypatch):
    monkeypatch.setenv("SDL_ALLOWED_ORIGINS", " https://a.example.com/ , https://b.example.com,, ")
    assert config.allowed_origins() == ["https://a.example.com", "https://b.example.com"]


def test_cors_allows_only_the_configured_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("SDL_ALLOWED_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    client = TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))
    ok = client.get("/api/loop", headers={"Origin": "https://console.example.com"})
    assert ok.headers.get("access-control-allow-origin") == "https://console.example.com"
    other = client.get("/api/loop", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" not in other.headers


