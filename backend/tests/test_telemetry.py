"""Tracing must never break the app: off in tests, safe when Phoenix is down, and the seed fixture is sound."""
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import seed_phoenix, telemetry


def test_tracing_is_off_under_pytest():
    assert telemetry.tracing_requested() is False
    assert telemetry.init_tracing() is False


def test_init_degrades_when_phoenix_is_down(monkeypatch):
    monkeypatch.setenv("SDL_TRACING", "on")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:1")  # nothing listens here
    assert telemetry.init_tracing() is False
    assert telemetry.is_enabled() is False


def test_span_helper_is_safe_without_a_provider():
    with telemetry.span("x", campaign_id="CAMP-014", cv_confidence=0.71, scientist_override=False, skipped=None):
        pass


def test_span_records_attributes_and_errors():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("t")
    # Route the helper's tracer through our in-memory provider.
    import app.telemetry as tel

    original = tel.trace.get_tracer
    tel.trace.get_tracer = lambda name, *a, **k: tracer
    try:
        with tel.span("ok", campaign_id="CAMP-014", policy_status="Blocked"):
            pass
        with pytest.raises(ValueError):
            with tel.span("boom"):
                raise ValueError("bad")
        with pytest.raises(KeyError):
            with tel.span("paused", passthrough=(KeyError,)):
                raise KeyError("pause")
    finally:
        tel.trace.get_tracer = original
    by_name = {s.name: s for s in exporter.get_finished_spans()}
    assert by_name["ok"].attributes["policy_status"] == "Blocked"
    assert by_name["boom"].status.status_code.name == "ERROR"
    assert by_name["paused"].status.status_code.name == "UNSET"  # a pause is not an error


def test_graph_runs_traced_nodes_without_a_provider():
    from app.graph import retrieve_context

    out = retrieve_context({"campaign_id": "CAMP-014"})
    assert out["history"]


def test_seed_fixture_matches_the_requested_taxonomy():
    t = seed_phoenix.SEED_TRACES
    assert len(t) == 6
    assert sum(1 for x in t if x.first_failure == "none") == 2  # two clean passes
    assert any(x.policy_rule == "RESTRICTED_ELEMENT" for x in t)
    assert any(x.policy_rule == "DUPLICATE_CONDITION" and x.composition == "Nb50-Ti20-Cr15-Al15" for x in t)
    fp = [x for x in t if x.triage_status == "Yellow"]
    assert len(fp) == 1 and fp[0].cv_confidence == 0.94 and fp[0].outcome == "Fail"
    assert any(x.outcome == "Fail" and x.expected_status == "Yellow" for x in t)  # missed blurry scan
    assert {x.outcome for x in t} == {"Pass", "Fail"}
    assert len({x.key for x in t}) == 6


def test_dataset_examples_line_up():
    ids = {x.key: f"{i:016x}" for i, x in enumerate(seed_phoenix.SEED_TRACES)}
    inputs, outputs, metadata = seed_phoenix.dataset_examples(ids)
    assert len(inputs) == len(outputs) == len(metadata) == 6
    assert all(m["illustrative"] and m["source_project"] == "sdl-control-plane-seed" for m in metadata)
    assert seed_phoenix.DATASET_NAME == "sdl-golden-eval-v1"
