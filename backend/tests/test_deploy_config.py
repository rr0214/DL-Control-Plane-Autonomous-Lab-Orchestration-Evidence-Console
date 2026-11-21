"""Deploy settings: CORS origins, the public Phoenix URL, the shared password and the daily run limit. No network."""
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


# ---- Phoenix links and the reachability check ------------------------------------------------------

from app import telemetry  # noqa: E402


def test_phoenix_public_url_defaults_to_localhost_and_is_configurable(monkeypatch, tmp_path):
    monkeypatch.delenv("PHOENIX_PUBLIC_URL", raising=False)
    assert telemetry.public_url() == "http://localhost:6006"
    monkeypatch.setenv("PHOENIX_PUBLIC_URL", "https://phoenix.example.com/")
    assert telemetry.public_url() == "https://phoenix.example.com"
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    client = TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))
    assert client.get("/api/health").json()["phoenix_url"] == "https://phoenix.example.com"


def test_phoenix_reachable_uses_443_for_https_and_80_for_http_without_a_port(monkeypatch):
    seen = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(telemetry.socket, "create_connection", lambda addr, timeout: seen.append(addr) or Conn())
    assert telemetry.phoenix_reachable("https://phoenix.example.com")
    assert telemetry.phoenix_reachable("http://phoenix.example.com")
    assert telemetry.phoenix_reachable("http://localhost:6006")
    assert seen == [("phoenix.example.com", 443), ("phoenix.example.com", 80), ("localhost", 6006)]


def test_tracing_is_skipped_quietly_when_phoenix_is_down(monkeypatch):
    def refuse(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(telemetry.socket, "create_connection", refuse)
    monkeypatch.setitem(telemetry._state, "enabled", False)
    monkeypatch.setenv("SDL_TRACING", "on")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://phoenix.example.com")
    assert telemetry.phoenix_reachable() is False
    assert telemetry.init_tracing() is False


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


# ---- daily run limit ----------------------------------------------------------------------------------

from app import db  # noqa: E402


def _plan_client(monkeypatch, tmp_path, limit: str | None) -> TestClient:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # mock plans: no Claude calls in tests
    monkeypatch.delenv("SDL_ACCESS_PASSWORD", raising=False)
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    if limit is None:
        monkeypatch.delenv("SDL_DAILY_RUN_LIMIT", raising=False)
    else:
        monkeypatch.setenv("SDL_DAILY_RUN_LIMIT", limit)
    return TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))


def _plan(client: TestClient):
    return client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014"})


def test_daily_run_limit_setting(monkeypatch):
    monkeypatch.delenv("SDL_DAILY_RUN_LIMIT", raising=False)
    assert config.daily_run_limit() == 0
    monkeypatch.setenv("SDL_DAILY_RUN_LIMIT", " 25 ")
    assert config.daily_run_limit() == 25
    for bad in ("ten", "2.5", "-1"):
        monkeypatch.setenv("SDL_DAILY_RUN_LIMIT", bad)
        with pytest.raises(ValueError):
            config.daily_run_limit()


def test_no_limit_by_default(monkeypatch, tmp_path):
    client = _plan_client(monkeypatch, tmp_path, None)
    assert all(_plan(client).status_code == 200 for _ in range(3))


def test_runs_past_the_daily_limit_get_429_and_reset_demo_does_not_clear_the_count(monkeypatch, tmp_path):
    client = _plan_client(monkeypatch, tmp_path, "2")
    assert _plan(client).status_code == 200
    assert _plan(client).status_code == 200
    over = _plan(client)
    assert over.status_code == 429
    assert over.json()["detail"] == "Daily run limit reached (2 of 2 today). It resets at midnight UTC."
    assert client.post("/api/demo/reset", headers={"X-Role": "Scientist (PI)"}).status_code == 200
    assert _plan(client).status_code == 429


def test_a_rejected_request_does_not_use_up_a_run(monkeypatch, tmp_path):
    client = _plan_client(monkeypatch, tmp_path, "1")
    assert client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-999"}).status_code == 404
    assert _plan(client).status_code == 200


def test_the_count_is_per_utc_day(tmp_path):
    conn = db.connect(str(tmp_path / "sdl.db"))
    try:
        assert db.take_run(conn, 1, day="2026-11-20") == (True, 1)
        assert db.take_run(conn, 1, day="2026-11-20") == (False, 1)
        assert db.take_run(conn, 1, day="2026-11-21") == (True, 1)
    finally:
        conn.close()
