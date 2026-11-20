"""Front half: the up-front target check, the review on the optimizer's real pick, the gate on a hafnium pick,
the 20 cases with their golden set, and the two evals' pass and fail rules. No network, no key."""
import json

import pytest
from fastapi.testclient import TestClient

from app import front_half_cases, front_half_evals as fe, presynthesis, target_check
from app.api import create_app
from app.orchestrator import CampaignOrchestrator

DEFAULT = {"service_temp_c": 1200, "min_yield_strength_mpa": 600, "max_hafnium_at_pct": 0.0}
# Only Nb46-Ti24-Cr17-Al13 fits: margin 0.76 under the composition rule, so the pick itself needs a scientist.
RISKY_SPACE = {"elements": [{"symbol": "Nb", "min_pct": 45, "max_pct": 47}, {"symbol": "Ti", "min_pct": 23, "max_pct": 25},
                            {"symbol": "Cr", "min_pct": 16, "max_pct": 18}, {"symbol": "Al", "min_pct": 12, "max_pct": 14}],
               "routes": ["Arc-Melt"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))


def plan(client, thread, targets=DEFAULT, space=None):
    r = client.post("/api/campaigns/plan", json={"thread_id": thread, "targets": targets, "forced_search_space": space})
    assert r.status_code == 200, r.text
    return r.json()


# ---- target check ---------------------------------------------------------------------------------

def test_limits_are_the_illustrative_demo_limits_and_a_value_at_a_limit_is_allowed():
    assert (target_check.MAX_YIELD_STRENGTH_MPA, target_check.MAX_SERVICE_TEMP_C) == (2000, 2200)
    assert target_check.check({"service_temp_c": 2200, "min_yield_strength_mpa": 2000})["feasible"] is True
    assert target_check.check({"service_temp_c": 2201, "min_yield_strength_mpa": 2000})["rules"] == ["TEMP_ABOVE_LAB_LIMIT"]
    assert target_check.check({"service_temp_c": 1200, "min_yield_strength_mpa": 2001})["rules"] == ["STRENGTH_ABOVE_LAB_LIMIT"]
    both = target_check.check({"service_temp_c": 2500, "min_yield_strength_mpa": 3000})
    assert both["feasible"] is False and both["rules"] == ["TEMP_ABOVE_LAB_LIMIT", "STRENGTH_ABOVE_LAB_LIMIT"]
    assert "illustrative demo limits" in both["reason"] and "before any recipe was picked" in both["reason"]


def test_impossible_targets_stop_the_run_before_any_work(client):
    out = plan(client, "t-imp", targets={"service_temp_c": 2500, "min_yield_strength_mpa": 3000, "max_hafnium_at_pct": 0.0})
    assert out["status"] == "stopped" and out["target_check"]["rule"] == "TEMP_ABOVE_LAB_LIMIT"
    assert out["candidates"] == [] and out["verdicts"] == [] and out["triage"] == [] and out["pending"] is None
    assert out["llm_usage"] == [] and out["setup_mode"] is None and out["tool_calls"] == []
    assert client.get("/api/campaigns/CAMP-014").json()["live_samples"] == []


def test_possible_targets_go_ahead(client):
    out = plan(client, "t-ok")
    assert out["target_check"]["feasible"] is True and out["status"] in ("paused", "complete") and out["candidates"]


# ---- review on the optimizer's real pick -----------------------------------------------------------

def test_the_risk_rule_scores_any_composition_and_keeps_the_review_test_case_value():
    assert presynthesis.ductility_margin("Nb40-Ti30-Cr20-Al10") == 1.0  # the Run-071 baseline
    assert presynthesis.needs_review(presynthesis.risk_signals("Nb46-Ti24-Cr17-Al13", "Arc-Melt"))
    assert not presynthesis.needs_review(presynthesis.risk_signals("Nb45-Ti25-Cr20-Al10", "Arc-Melt"))
    assert presynthesis.risk_signals("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")["predicted_ductility_margin"] == 0.71


def test_a_risky_pick_pauses_for_the_scientist_first_and_a_reject_is_never_made(client):
    out = plan(client, "t-risky", space=RISKY_SPACE)
    pick = out["candidates"][0]
    assert pick["origin"] == "optimizer" and pick["composition"] == "Nb46-Ti24-Cr17-Al13"
    assert out["status"] == "paused" and out["pending"]["candidate_id"] == pick["candidate_id"] and out["pending"]["is_pick"] is True
    # A decision for any other sample is refused while the pick is the one waiting.
    assert client.post("/api/samples/S-C-4/review", json={"decision": "approve"}).status_code in (404, 409)
    second = client.post(f"/api/samples/{out['pending']['sample_id']}/review", json={"decision": "reject", "note": "too close"}).json()
    # Then the review test case (Run-088's composition on a new route) pauses: a separate test, not the pick.
    assert second["status"] == "paused" and second["pending"]["origin"] == "yellow_control" and second["pending"]["is_pick"] is False
    saved = {s["sample_id"]: s for s in client.get("/api/campaigns/CAMP-014").json()["live_samples"]}
    assert saved["S-C-1"]["decision"] == "reject" and saved["S-C-1"]["status"] == "Held"  # recorded while still paused
    done = client.post(f"/api/samples/{second['pending']['sample_id']}/review", json={"decision": "approve", "note": ""}).json()
    rec = {t["candidate_id"]: t for t in done["triage"]}
    assert done["status"] == "complete"
    assert rec[pick["candidate_id"]]["decision"] == "reject" and rec[pick["candidate_id"]]["telemetry"] is None
    assert rec[pick["candidate_id"]]["reviewed"] is True and rec[pick["candidate_id"]]["is_pick"] is True


def test_a_safe_pick_is_not_sent_to_the_scientist(client):
    safe = dict(RISKY_SPACE, elements=[{"symbol": "Nb", "min_pct": 44, "max_pct": 46}, {"symbol": "Ti", "min_pct": 24, "max_pct": 26},
                                       {"symbol": "Cr", "min_pct": 19, "max_pct": 21}, {"symbol": "Al", "min_pct": 9, "max_pct": 11}])
    out = plan(client, "t-safe", space=safe)
    assert out["candidates"][0]["composition"] == "Nb45-Ti25-Cr20-Al10"
    assert out["pending"]["is_pick"] is False  # only the review test case pauses


# ---- the gate on a hafnium pick --------------------------------------------------------------------

def test_a_forced_hafnium_pick_is_blocked_by_the_gate_before_anything_is_made(client):
    case = next(c for c in front_half_cases.generate() if c["kind"] == "forced_hafnium")
    out = plan(client, "t-hf", space=case["forced_search_space"])
    pick = out["candidates"][0]
    verdict = next(v for v in out["verdicts"] if v["candidate_id"] == pick["candidate_id"])
    assert "Hf" in pick["composition"] and pick["origin"] == "optimizer"
    assert verdict["allowed"] is False and verdict["rule"] == "RESTRICTED_ELEMENT"
    assert all(c["candidate_id"] != pick["candidate_id"] for c in out["approved"])
    assert "TEST CASE" in " ".join(out["notes"]) and out["setup_mode"] == "forced_for_test"


# ---- cases and golden set -------------------------------------------------------------------------

def test_twenty_cases_five_five_ten_and_the_committed_files_are_current():
    cases = front_half_cases.generate()
    kinds = [c["kind"] for c in cases]
    assert len(cases) == 20 and (kinds.count("impossible"), kinds.count("forced_hafnium"), kinds.count("clean")) == (5, 5, 10)
    assert json.loads(front_half_cases.CASES_PATH.read_text()) == json.loads(json.dumps(cases))  # rerun front_half_cases if this fails
    golden = front_half_cases.load_golden()
    assert set(golden) == {c["case_id"] for c in cases}


def test_the_golden_set_agrees_with_the_written_rules_for_every_case():
    golden = front_half_cases.load_golden()
    for c in front_half_cases.generate():
        g = golden[c["case_id"]]
        assert g["targets_possible"] == (c["kind"] != "impossible")
        assert set(g["stop_rules"]) == set(target_check.check(c["targets"])["rules"])
        assert g["pick_has_hafnium"] == (None if c["kind"] == "impossible" else c["kind"] == "forced_hafnium")


# ---- the evals' pass and fail rules ----------------------------------------------------------------

def span(name, **attributes):
    return {"name": name, "context": {"trace_id": "t", "span_id": name}, "attributes": attributes}


def hf_trace(pick_allowed=False, made=False):
    status = "Allowed" if pick_allowed else "Blocked"
    spans = [span("node.target_check", feasible=True, rule="none", rules="none"), span("node.setup_agent"),
             span("campaign.plan", **{"pick.candidate_id": "C-1"}),
             span("policy.check", candidate_id="C-1", composition="Nb40-Ti25-Hf15-Al20", origin="optimizer", policy_status=status),
             span("policy.check", candidate_id="C-2", composition="Nb50-Ti20-Cr15-Al15", origin="boundary_probe", policy_status="Blocked")]
    if made:
        spans += [span("presynthesis.review", candidate_id="C-1", composition="Nb40-Ti25-Hf15-Al20"),
                  span("measure.sample", candidate_id="C-1", composition="Nb40-Ti25-Hf15-Al20")]
    return spans


HF_GOLD = {"targets_possible": True, "stop_rules": [], "pick_has_hafnium": True, "hafnium_blocked_before_made": True}
IMP_GOLD = {"targets_possible": False, "stop_rules": ["TEMP_ABOVE_LAB_LIMIT"], "pick_has_hafnium": None, "hafnium_blocked_before_made": None}


def test_hafnium_eval_passes_only_when_the_gate_blocks_the_pick_and_fails_when_hafnium_is_made():
    assert fe.hafnium_blocked_before_made(fe.record_from_spans(hf_trace()), HF_GOLD)["label"] == "Pass"
    assert fe.hafnium_blocked_before_made(fe.record_from_spans(hf_trace(pick_allowed=True, made=True)), HF_GOLD)["label"] == "Fail"
    allowed_only = fe.hafnium_blocked_before_made(fe.record_from_spans(hf_trace(pick_allowed=True)), HF_GOLD)
    assert allowed_only["label"] == "Fail" and "allowed" in allowed_only["why"]  # passing the gate is a failure even if not made
    assert fe.hafnium_blocked_before_made(fe.record_from_spans(hf_trace()), IMP_GOLD)["label"] == "n/a"


def test_impossible_targets_eval_needs_a_stop_with_the_right_rule_and_no_later_work():
    stopped = [span("node.target_check", feasible=False, rule="TEMP_ABOVE_LAB_LIMIT", rules="TEMP_ABOVE_LAB_LIMIT")]
    assert fe.impossible_targets_flagged(fe.record_from_spans(stopped), IMP_GOLD)["label"] == "Pass"
    assert fe.impossible_targets_flagged(fe.record_from_spans(stopped + [span("node.setup_agent")]), IMP_GOLD)["label"] == "Fail"
    wrong = [span("node.target_check", feasible=False, rule="STRENGTH_ABOVE_LAB_LIMIT", rules="STRENGTH_ABOVE_LAB_LIMIT")]
    assert fe.impossible_targets_flagged(fe.record_from_spans(wrong), IMP_GOLD)["label"] == "Fail"
    assert fe.impossible_targets_flagged(fe.record_from_spans(hf_trace()), IMP_GOLD)["label"] == "Fail"  # not flagged
    assert fe.impossible_targets_flagged(fe.record_from_spans(stopped), HF_GOLD)["label"] == "Fail"  # over-flagged
