import pytest

from app.chemistry import parse
from app.orchestrator import CampaignOrchestrator


@pytest.fixture
def orch(tmp_path, monkeypatch):
    # Force mock mode and an isolated database, regardless of the developer's .env.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return CampaignOrchestrator(str(tmp_path / "checkpoints.sqlite"))


def test_plan_pauses_for_review_before_any_sample_is_made(orch):
    out = orch.plan("CAMP-014", "thread-1")
    assert out["status"] == "paused"
    pending = out["pending"]
    assert pending["status"] == "Yellow" and pending["stage"] == "pre_synthesis"
    assert pending["options"] == ["approve", "revise", "reject"]
    assert "2.1% elongation" in pending["reason"] and "high" in pending["reason"]
    assert "before any sample is made" in pending["reason"]
    # No scan data exists yet: the recipe has not been synthesized.
    assert "telemetry" not in pending
    assert out["triage"] == []
    assert pending["risk"]["predicted_ductility_margin"] == 0.71
    assert pending["risk"]["restricted_elements"] == []


def test_review_resumes_and_gate_blocks_both_test_routes(orch):
    orch.plan("CAMP-014", "thread-2")
    done = orch.review("thread-2", "approve", "Margin is fine for this furnace, go ahead")

    assert done["status"] == "complete"
    assert done["llm_mode"] == "mock"
    assert done["triage"][0]["decision"] == "approve"
    assert done["triage"][0]["intuition_note"] == "Margin is fine for this furnace, go ahead"
    # Approved, so it was synthesized and scanned. The ambiguous scan is flagged but does not pause again.
    assert done["triage"][0]["telemetry"]["sem_cv_confidence"] == 0.71
    assert done["triage"][0]["status"] == "Yellow"
    assert "does not block" in done["triage"][0]["follow_up"]

    blocked = {v["rule"] for v in done["verdicts"] if not v["allowed"]}
    assert blocked == {"DUPLICATE_CONDITION", "RESTRICTED_ELEMENT"}

    allowed = [c for c, v in zip(done["candidates"], done["verdicts"]) if v["allowed"]]
    assert len(allowed) == 1
    assert allowed[0]["processing"] == "Additive/Anneal"


def test_every_ratio_comes_from_optimizer_and_sums_to_100(orch):
    orch.plan("CAMP-014", "thread-3")
    done = orch.review("thread-3", "reject")
    assert len(done["candidates"]) == 3
    for c in done["candidates"]:
        assert c["source"] == "propose_alloy_ratios"
        assert sum(parse(c["composition"]).values()) == 100


@pytest.mark.parametrize("decision", ["reject", "revise"])
def test_reject_or_revise_holds_the_recipe_and_never_synthesizes(orch, decision):
    orch.plan("CAMP-014", f"thread-{decision}")
    done = orch.review(f"thread-{decision}", decision, "Too risky for the furnace")
    assert done["status"] == "complete"
    rec = done["triage"][0]
    assert rec["decision"] == decision and rec["status"] == "Held"
    assert rec["telemetry"] is None  # no scan: nothing was made
    assert "Not synthesized" in rec["follow_up"]


def test_low_risk_recipes_skip_review_and_are_synthesized(orch, monkeypatch):
    from app import presynthesis

    monkeypatch.setattr(presynthesis, "needs_review", lambda signals: False)
    out = orch.plan("CAMP-014", "thread-lowrisk")
    assert out["status"] == "complete" and out["pending"] is None
    assert out["triage"][0]["telemetry"] is not None


def test_review_span_records_everything_the_scientist_sees(orch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    import app.telemetry as tel

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("t")
    original = tel.trace.get_tracer
    tel.trace.get_tracer = lambda name, *a, **k: tracer
    try:
        orch.plan("CAMP-014", "thread-trace")
    finally:
        tel.trace.get_tracer = original
    span = next(s for s in exporter.get_finished_spans() if s.name == "presynthesis.review" and s.attributes["review_required"])
    a = span.attributes
    assert a["predicted_elongation_pct"] == 2.1 and a["baseline_elongation_pct"] == 3.0 and a["min_elongation_pct"] == 2.4
    assert a["furnace_blast_radius"] == "high" and a["baseline_run"] == "Run-071"
    assert a["ductility_label"] == "borderline" and a["phase_stability"] == 0.97
