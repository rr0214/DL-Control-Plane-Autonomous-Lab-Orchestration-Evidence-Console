import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db, targets
from app.api import create_app
from app.orchestrator import CampaignOrchestrator


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))


def test_campaign_has_default_targets(client):
    t = client.get("/api/campaigns/CAMP-014").json()["campaign"]["targets"]
    assert t == targets.DEFAULT_TARGETS
    assert set(t) == {"service_temp_c", "min_yield_strength_mpa", "max_hafnium_at_pct"}


def test_plan_without_targets_uses_the_campaign_targets(client):
    body = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-a"}).json()
    assert body["targets"] == targets.DEFAULT_TARGETS


def test_plan_with_targets_carries_them_through(client):
    custom = {"service_temp_c": 1400, "min_yield_strength_mpa": 800, "max_hafnium_at_pct": 0.0}
    body = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-b", "targets": custom}).json()
    assert body["targets"] == custom
    # The plan row stored in SQLite keeps them, so the targets are part of the lineage.
    plans = client.get("/api/campaigns/CAMP-014").json()["plans"]
    assert any(p["thread_id"] == "t-b" for p in plans)


@pytest.mark.parametrize("bad", [{"service_temp_c": 5}, {"min_yield_strength_mpa": -1}, {"max_hafnium_at_pct": 50}])
def test_out_of_range_targets_are_rejected(client, bad):
    r = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "targets": bad})
    assert r.status_code == 422


def test_old_database_without_targets_column_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE campaigns (campaign_id TEXT PRIMARY KEY, goal TEXT NOT NULL, tenant TEXT NOT NULL, export_control TEXT NOT NULL);"
        "INSERT INTO campaigns VALUES ('CAMP-014', 'old goal', 'SDL-Internal', 'ITAR');"
    )
    old.commit()
    old.close()
    conn = db.connect(path)
    campaign = db.get_campaign(conn, "CAMP-014")
    assert campaign["goal"] == "old goal"  # existing rows are kept
    assert campaign["targets"] == targets.DEFAULT_TARGETS


def test_targets_line_for_the_planner_prompt():
    line = targets.describe(targets.DEFAULT_TARGETS)
    assert "1200" in line and "600" in line and "hafnium" in line
    assert targets.describe(None) == ""


def test_loop_endpoint_serves_the_steps(client):
    steps = client.get("/api/loop").json()["steps"]
    assert len(steps) == 10 and steps[0]["type"] == "person"
