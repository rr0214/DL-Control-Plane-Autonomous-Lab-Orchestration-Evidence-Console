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


# ---- shared access password ------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.fixture
def locked(monkeypatch, tmp_path):
    monkeypatch.setenv("SDL_ACCESS_PASSWORD", "open sesame")
    monkeypatch.setenv("SDL_ALLOWED_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))


def test_with_a_password_every_api_route_needs_the_header(locked):
    for path in ("/api/health", "/api/loop", "/api/campaigns/CAMP-014", "/docs"):
        assert locked.get(path).status_code == 401, path
        assert locked.get(path, headers={"X-Access-Password": "wrong"}).status_code == 401, path
    assert locked.post("/api/campaigns/plan", json={}).status_code == 401
    assert locked.get("/api/loop", headers={"X-Access-Password": "open sesame"}).status_code == 200


def test_health_stays_open_and_a_401_still_carries_cors_headers(locked):
    assert locked.get("/health").json() == {"status": "ok"}
    r = locked.get("/api/loop", headers={"Origin": "https://console.example.com"})
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == "https://console.example.com"
    pre = locked.options("/api/loop", headers={"Origin": "https://console.example.com", "Access-Control-Request-Method": "GET",
                                               "Access-Control-Request-Headers": "x-access-password"})
    assert pre.status_code == 200


def test_without_a_password_nothing_changes(monkeypatch, tmp_path):
    monkeypatch.delenv("SDL_ACCESS_PASSWORD", raising=False)
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    client = TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))
    assert client.get("/api/loop").status_code == 200 and client.get("/health").status_code == 200


