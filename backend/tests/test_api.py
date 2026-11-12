import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.orchestrator import CampaignOrchestrator


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    orch = CampaignOrchestrator(str(tmp_path / "checkpoints.sqlite"))
    return TestClient(create_app(orch))


def test_get_campaign_returns_rbac_receipts_and_trace(client):
    r = client.get("/api/campaigns/CAMP-014")
    assert r.status_code == 200
    body = r.json()
    assert body["campaign"]["tenant"] == "SDL-Internal"
    assert body["campaign"]["export_control"] == "ITAR"
    assert len(body["rbac"]["roles"]) == 4
    assert all(len(s["receipt"]["content_sha256"]) == 64 for s in body["seed_samples"])
    names = {span["name"] for span in body["seed_trace"]["spans"]}
    assert {"campaign.plan", "policy_kernel", "triage_and_hitl"} <= names


def test_unknown_campaign_returns_404(client):
    assert client.get("/api/campaigns/CAMP-999").status_code == 404


def test_plan_pauses_persists_and_shows_in_get(client):
    r = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "paused"
    assert body["pending"]["sample_id"] == "S-C-3"
    assert body["trace"]["simulated"] is True

    live = client.get("/api/campaigns/CAMP-014").json()["live_samples"]
    pending = [s for s in live if s["sample_id"] == "S-C-3"]
    assert pending and pending[0]["decision"] is None
    assert pending[0]["receipt"]["content_sha256"]


def test_review_enforces_rbac_then_resumes(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-2"})

    denied = client.post(
        "/api/samples/S-C-3/review",
        json={"decision": "approve", "note": "looks fine"},
        headers={"X-Role": "Operator"},
    )
    assert denied.status_code == 403

    done = client.post(
        "/api/samples/S-C-3/review",
        json={"decision": "approve", "note": "Phase looks right"},
        headers={"X-Role": "Scientist (PI)"},
    )
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "complete"
    assert body["triage"][-1]["decision"] == "approve"

    live = client.get("/api/campaigns/CAMP-014").json()["live_samples"]
    assert [s for s in live if s["sample_id"] == "S-C-3"][0]["decision"] == "approve"


def test_review_unknown_or_already_decided_sample(client):
    assert client.post("/api/samples/S-NOPE/review", json={"decision": "kill"}).status_code == 404

    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-3"})
    client.post("/api/samples/S-C-3/review", json={"decision": "kill", "note": ""})
    again = client.post("/api/samples/S-C-3/review", json={"decision": "approve", "note": ""})
    assert again.status_code == 409


def test_duplicate_thread_id_rejected(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-4"})
    r = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-4"})
    assert r.status_code == 409
