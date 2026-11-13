"""Eval logic is plain code, so it is tested without Phoenix. The dataset labels are illustrative."""
from app import presynthesis, run_evals as ev


def test_dataset_rows_line_up_and_carry_a_known_failure_mode():
    inputs, outputs, metadata = ev.dataset_examples()
    assert len(inputs) == len(outputs) == len(metadata) == len(ev.ROWS)
    assert all(m["failure_mode"] in ev.FAILURE_MODES for m in metadata)
    assert all(m["illustrative"] is True for m in metadata)


def test_task_matches_the_production_review_decision_at_the_default_threshold():
    for _key, comp, proc, *_ in ev.ROWS:
        out = ev.run_system(comp, proc)
        if out["policy"] == "Allowed":
            risk = presynthesis.risk_signals(comp, proc)
            assert out["review_required"] == presynthesis.needs_review(risk)


def test_gate_blocks_are_scored_correctly():
    out = ev.run_system("Nb40-Ti25-Hf15-Al20", "Arc-Melt")
    assert (out["policy"], out["rule"]) == ("Blocked", "RESTRICTED_ELEMENT")
    out = ev.run_system("Nb50-Ti20-Cr15-Al15", "Arc-Melt")
    assert (out["policy"], out["rule"]) == ("Blocked", "DUPLICATE_CONDITION")


def test_default_threshold_finds_exactly_the_known_gap():
    failed = [r["scenario"] for r in ev.score_rows(ev.DEFAULT_THRESHOLD) if not r["passed"]]
    assert failed == ["missed-risk"]  # the mock risk model has no entry for this recipe


def test_a_stricter_threshold_trades_a_caught_risk_for_more_noise():
    rows = {r["scenario"]: r for r in ev.score_rows(ev.COMPARE_THRESHOLD)}
    assert rows["missed-risk"]["passed"] is True  # now flagged
    assert rows["safe-but-novel"]["passed"] is False  # but safe recipes are flagged too
    strict = sum(r["passed"] for r in rows.values())
    default = sum(r["passed"] for r in ev.score_rows(ev.DEFAULT_THRESHOLD))
    assert strict < default


def test_evaluators_return_binary_labels_and_explanations():
    out = {"policy": "Allowed", "rule": "PASS", "review_required": True, "margin": 0.92}
    exp = {"expected_policy": "Allowed", "expected_rule": "PASS", "expected_review": False}
    assert ev.gate_correct(out, exp)["label"] == "Pass"
    bad = ev.review_correct(out, exp)
    assert bad["label"] == "Fail" and bad["score"] == 0.0 and "0.92" in bad["explanation"]


def test_main_exits_clearly_when_phoenix_is_down(monkeypatch, capsys):
    from app import telemetry
    monkeypatch.setattr(telemetry, "phoenix_reachable", lambda *a, **k: False)
    assert ev.main([]) == 1
    assert "Cannot reach Phoenix" in capsys.readouterr().out


def test_local_mode_never_touches_phoenix(capsys):
    assert ev.main(["--local", "--compare"]) == 0
    assert "Review threshold 0.80" in capsys.readouterr().out


def test_summary_matches_the_experiment_scoring_and_is_labeled_illustrative():
    s = ev.summary()
    by_t = {r["threshold"]: r for r in s["runs"]}
    assert (by_t[0.8]["passed"], by_t[0.8]["total"]) == (6, 7)
    assert (by_t[0.95]["passed"], by_t[0.95]["total"]) == (4, 7)
    assert "illustrative" in s["labels"] and "none" not in s["failure_modes"] and len(s["failure_modes"]) == 4


def test_evals_summary_endpoint_is_read_only_and_works_without_phoenix(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import create_app
    from app.orchestrator import CampaignOrchestrator

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    client = TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))
    body = client.get("/api/evals/summary").json()
    assert body["dataset"] == "sdl-golden-eval-v2" and len(body["runs"]) == 2
    assert client.post("/api/evals/summary").status_code == 405
