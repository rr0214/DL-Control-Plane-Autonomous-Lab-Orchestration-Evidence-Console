import pytest
from fastapi.testclient import TestClient

from app import db
from app.api import create_app
from app.orchestrator import CampaignOrchestrator


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    orch = CampaignOrchestrator(str(tmp_path / "checkpoints.sqlite"))
    return TestClient(create_app(orch))


def test_health_reports_mcp_mode(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["mcp_mode"] in {"fastmcp", "direct"}


def test_get_campaign_returns_rbac_receipts_literature_and_trace(client):
    r = client.get("/api/campaigns/CAMP-014")
    assert r.status_code == 200
    body = r.json()
    assert body["campaign"]["tenant"] == "SDL-Internal"
    assert body["campaign"]["export_control"] == "ITAR"
    assert len(body["rbac"]["roles"]) == 4
    assert all(len(s["receipt"]["content_sha256"]) == 64 for s in body["seed_samples"])
    assert body["literature"] and all(lit["doi_url"].startswith("https://doi.org/") for lit in body["literature"])
    names = {span["name"] for span in body["seed_trace"]["spans"]}
    assert {"campaign.plan", "policy_kernel", "triage_and_hitl"} <= names


def test_unknown_campaign_returns_404(client):
    assert client.get("/api/campaigns/CAMP-999").status_code == 404


def test_plan_pauses_persists_and_traces_mcp_calls(client):
    r = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "paused"
    assert body["pending"]["sample_id"] == "S-C-3"
    assert body["trace"]["simulated"] is True
    span_names = {s["name"] for s in body["trace"]["spans"]}
    assert "mcp.propose_alloy_ratios" in span_names
    assert "mcp.check_negative_runs" in span_names

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
    assert client.post("/api/samples/S-NOPE/review", json={"decision": "reject"}).status_code == 404

    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-3"})
    client.post("/api/samples/S-C-3/review", json={"decision": "reject", "note": ""})
    again = client.post("/api/samples/S-C-3/review", json={"decision": "approve", "note": ""})
    assert again.status_code == 409


def test_duplicate_thread_id_rejected(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-4"})
    r = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-4"})
    assert r.status_code == 409


def test_reset_clears_campaign_lineage_but_keeps_seed_runs(client, tmp_path, monkeypatch):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-5"})
    assert client.get("/api/campaigns/CAMP-014").json()["live_samples"]

    denied = client.post("/api/demo/reset", headers={"X-Role": "Operator"})
    assert denied.status_code == 403

    r = client.post("/api/demo/reset", headers={"X-Role": "Scientist (PI)"})
    assert r.status_code == 200
    assert r.json()["threads_cleared"] == 1

    body = client.get("/api/campaigns/CAMP-014").json()
    assert body["live_samples"] == []
    assert body["plans"] == []

    conn = db.connect()
    try:
        assert {run["run_id"] for run in db.get_runs(conn, "CAMP-014")} == {"Run-071", "Run-088"}
    finally:
        conn.close()

    # A fresh plan works after reset and pauses on the Yellow control again.
    again = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-6"})
    assert again.json()["status"] == "paused"


def test_operator_may_revise_but_not_approve_or_reject(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-rbac"})
    op = {"X-Role": "Operator"}
    assert client.post("/api/samples/S-C-3/review", json={"decision": "approve"}, headers=op).status_code == 403
    assert client.post("/api/samples/S-C-3/review", json={"decision": "reject"}, headers=op).status_code == 403
    assert client.post("/api/samples/S-C-3/review", json={"decision": "revise"}, headers=op).status_code == 200


def test_old_decision_names_are_no_longer_accepted(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-old"})
    for old in ("kill", "rescan"):
        assert client.post("/api/samples/S-C-3/review", json={"decision": old}).status_code == 422


def test_plan_response_is_paused_before_synthesis_with_risk_signals(client):
    body = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-pre"}).json()
    assert body["status"] == "paused" and body["pending"]["stage"] == "pre_synthesis"
    assert body["pending"]["risk"]["furnace_blast_radius"] == "high"
    assert "telemetry" not in body["pending"] and body["triage"] == []


def test_rejected_recipe_is_stored_as_held_with_a_no_instrument_receipt(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-held"})
    done = client.post("/api/samples/S-C-3/review", json={"decision": "reject", "note": "too risky"}).json()
    assert done["triage"][-1]["status"] == "Held" and done["triage"][-1]["telemetry"] is None
    sample = [s for s in client.get("/api/campaigns/CAMP-014").json()["live_samples"] if s["sample_id"] == "S-C-3"][0]
    assert sample["decision"] == "reject" and sample["status"] == "Held"
    assert sample["receipt"]["instrument"] == "none (held before synthesis)"
    assert len(sample["receipt"]["content_sha256"]) == 64


def test_repeated_plan_without_reset_attaches_the_sample_to_the_newest_thread(client):
    # Each plan reuses the sample id S-C-3. The review must resume the NEWEST plan, not the first one.
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-first"})
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-second"})
    done = client.post("/api/samples/S-C-3/review", json={"decision": "approve", "note": ""}).json()
    assert done["thread_id"] == "t-second"
    plans = {p["thread_id"]: p["status"] for p in client.get("/api/campaigns/CAMP-014").json()["plans"]}
    assert plans["t-second"] == "complete" and plans["t-first"] == "paused"
