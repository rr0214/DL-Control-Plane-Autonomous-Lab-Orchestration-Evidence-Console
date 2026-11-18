"""S5: release checkpoint. Compare to customer targets, scientist sign-off, receipt."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import graph, history, measure, release
from app.api import create_app
from app.orchestrator import CampaignOrchestrator
from app import db

TARGETS = {"service_temp_c": 1200, "min_yield_strength_mpa": 600, "max_hafnium_at_pct": 0.0}


def m(hv=420.0, ox=3.0, hf=0.0):
    comp = {"Nb": 50.0, "Ti": 20.0, "Cr": 15.0, "Al": 15.0}
    if hf:
        comp["Hf"] = hf
    return {"composition_at_pct": comp, "hardness_hv": hv, "oxidation_mg_cm2": ox}


def sample(status="Green", **kw):
    return {"sample_id": "S-1", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "status": status, "measurements": m(**kw)}


# ---- comparison -------------------------------------------------------------------------------

def test_all_assessed_targets_met_and_temperature_is_not_assessed():
    c = release.compare(TARGETS, m())
    assert c["all_met"] and [r["passed"] for r in c["rows"]] == [None, True, True]
    assert c["not_assessed"] == ["service_temp_c"]


def test_temperature_is_never_a_pass_or_a_fail_whatever_the_oxidation():
    for ox in (0.5, 3.0, 9.0):
        row = release.compare(TARGETS, m(ox=ox))["rows"][0]
        assert row["passed"] is None and row["value"] is None and row["basis"] == "not assessed until measured"


def test_strength_and_hafnium_can_each_fail_on_their_own():
    assert [r["passed"] for r in release.compare(TARGETS, m(hv=150))["rows"]] == [None, False, True]   # strength
    assert [r["passed"] for r in release.compare(TARGETS, m(hf=0.3))["rows"]] == [None, True, False]   # hafnium
    assert release.compare(dict(TARGETS, max_hafnium_at_pct=0.5), m(hf=0.3))["rows"][2]["passed"]


def test_every_row_says_what_it_rests_on():
    bases = {r["key"]: r["basis"] for r in release.compare(TARGETS, m())["rows"]}
    assert bases["min_yield_strength_mpa"].startswith("estimated") and bases["max_hafnium_at_pct"].startswith("measured")


# ---- rules ------------------------------------------------------------------------------------

def test_clean_green_sample_needs_no_note_even_though_temperature_is_not_assessed():
    ev = release.evaluate(TARGETS, sample(), None)
    assert ev["exceptions"] == [] and not ev["needs_note"] and release.decide(ev, "release", "")["ok"]
    r = release.make_receipt(sample(), TARGETS, ev, "release", "", "Scientist (PI)")
    assert r["payload"]["not_assessed"] == ["service_temp_c"]  # recorded in the receipt, not hidden


def test_exceptions_need_a_written_reason():
    ev = release.evaluate(TARGETS, sample("Yellow", hv=150), {"final_action": "hold"})
    assert ev["exceptions"] == ["target_missed:min_yield_strength_mpa", "status_yellow", "diagnosis_hold"]
    v = release.decide(ev, "release", "ok")
    assert not v["ok"] and v["rule"] == "NOTE_REQUIRED"
    assert release.decide(ev, "release", "Customer accepts lower temperature for this lot")["ok"]


def test_withholding_never_needs_a_note():
    ev = release.evaluate(TARGETS, sample("Yellow", hv=150), None)
    assert release.decide(ev, "withhold", "")["ok"]


def test_red_can_never_be_released_even_with_a_note():
    ev = release.evaluate(TARGETS, sample("Red"), None)
    v = release.decide(ev, "release", "Please release this anyway, it is fine really")
    assert not v["ok"] and v["rule"] == "RED_NO_RELEASE" and ev["blocked_rule"] == "RED_NO_RELEASE"
    assert release.decide(ev, "withhold", "")["ok"]


def test_unknown_decision_is_refused():
    assert release.decide(release.evaluate(TARGETS, sample(), None), "ship", "")["rule"] == "INVALID_DECISION"


def test_receipt_hash_covers_the_decision_and_changes_if_anything_changes():
    ev = release.evaluate(TARGETS, sample(), None)
    r = release.make_receipt(sample(), TARGETS, ev, "release", "fine", "Scientist (PI)")
    assert hashlib.sha256(json.dumps(r["payload"], sort_keys=True).encode()).hexdigest() == r["content_sha256"]
    assert r["receipt_id"] == "RCPT-REL-" + r["content_sha256"][:12]
    other = release.make_receipt(sample(), TARGETS, ev, "withhold", "fine", "Scientist (PI)")
    assert other["content_sha256"] != r["content_sha256"] and "not real authentication" in r["note"]


# ---- API --------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))


def made_sample(client, thread="t-1", targets=None):
    body = {"campaign_id": "CAMP-014", "thread_id": thread}
    if targets:
        body["targets"] = targets
    client.post("/api/campaigns/plan", json=body)
    client.post("/api/samples/S-C-3/review", json={"decision": "approve", "note": ""})
    return "S-C-3"


def test_preview_shows_the_comparison_and_the_exceptions(client):
    sid = made_sample(client)
    p = client.get(f"/api/samples/{sid}/release").json()
    assert p["targets"] == TARGETS and p["release"] is None and p["min_note"] == release.MIN_NOTE
    assert "status_yellow" in p["evaluation"]["exceptions"] and "diagnosis_hold" in p["evaluation"]["exceptions"]
    assert p["evaluation"]["comparison"]["not_assessed"] == ["service_temp_c"]
    assert p["evaluation"]["needs_note"]


def test_release_uses_the_targets_the_plan_was_run_with(client):
    sid = made_sample(client, targets=dict(TARGETS, service_temp_c=1000, min_yield_strength_mpa=3000))
    rows = {r["key"]: r for r in client.get(f"/api/samples/{sid}/release").json()["evaluation"]["comparison"]["rows"]}
    assert rows["service_temp_c"]["requirement"] == "at least 1000 C" and rows["service_temp_c"]["passed"] is None
    assert rows["min_yield_strength_mpa"]["passed"] is False


def test_release_needs_a_note_then_succeeds_with_one_and_cannot_be_repeated(client):
    sid = made_sample(client)
    r = client.post(f"/api/samples/{sid}/release", json={"decision": "release", "note": ""})
    assert r.status_code == 409 and r.json()["detail"]["rule"] == "NOTE_REQUIRED"
    ok = client.post(f"/api/samples/{sid}/release", json={"decision": "release", "note": "Customer accepts a lower temperature for this lot"})
    assert ok.status_code == 200 and ok.json()["receipt"]["receipt_id"].startswith("RCPT-REL-")
    assert client.post(f"/api/samples/{sid}/release", json={"decision": "withhold", "note": ""}).status_code == 409
    saved = client.get("/api/campaigns/CAMP-014").json()["releases"]
    assert len(saved) == 1 and saved[0]["decision"] == "release" and saved[0]["receipt"]["payload"]["exceptions"]


def test_only_a_scientist_can_sign_off(client):
    sid = made_sample(client)
    for decision in ("release", "withhold"):
        r = client.post(f"/api/samples/{sid}/release", json={"decision": decision, "note": "x" * 20}, headers={"X-Role": "Operator"})
        assert r.status_code == 403
    assert client.get("/api/campaigns/CAMP-014").json()["releases"] == []


def test_withhold_works_without_a_note(client):
    sid = made_sample(client)
    assert client.post(f"/api/samples/{sid}/release", json={"decision": "withhold", "note": ""}).status_code == 200


def test_red_sample_returns_409_with_the_rule(client, monkeypatch):
    real = graph.check.run_checks
    monkeypatch.setattr(graph.check, "run_checks", lambda *a, **k: dict(real(*a, **k), severity="Red", flags=["readings_valid"]))
    sid = made_sample(client)
    r = client.post(f"/api/samples/{sid}/release", json={"decision": "release", "note": "Release it anyway please, thanks"})
    assert r.status_code == 409 and r.json()["detail"]["rule"] == "RED_NO_RELEASE"


def test_a_sample_that_was_never_made_has_nothing_to_release(client):
    client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-h"})
    client.post("/api/samples/S-C-3/review", json={"decision": "reject", "note": "no"})
    assert client.get("/api/samples/S-C-3/release").status_code == 409
    assert client.get("/api/samples/S-NOPE/release").status_code == 404


def test_release_decision_flows_back_to_the_planner_history(client):
    sid = made_sample(client)
    client.post(f"/api/samples/{sid}/release", json={"decision": "withhold", "note": "Oxidation too poor for the customer"})
    conn = db.connect()
    entry = next(r for r in history.planner_history(conn, "CAMP-014") if r["run_id"] == sid)
    assert entry["release"] == "withhold"
    line = history.format_line(entry)
    assert "release sign-off: withheld" in line and 'release note (quoted data): "Oxidation too poor for the customer"' in line


def test_reset_clears_releases(client):
    sid = made_sample(client)
    client.post(f"/api/samples/{sid}/release", json={"decision": "withhold", "note": ""})
    conn = db.connect()
    db.clear_campaign_lineage(conn, "CAMP-014")
    assert db.list_releases(conn, "CAMP-014") == []
