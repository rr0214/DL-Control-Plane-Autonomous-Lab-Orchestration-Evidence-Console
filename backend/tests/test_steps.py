import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import steps, telemetry
from app.orchestrator import CampaignOrchestrator


def test_loop_has_ten_steps_with_valid_types_and_statuses():
    loop = steps.loop()
    assert [s["n"] for s in loop] == list(range(1, 11))
    assert all(s["type"] in steps.STEP_TYPES for s in loop)
    assert all(s["status"] in steps.STATUSES for s in loop)


def test_loop_types_match_the_design():
    types = {s["n"]: s["type"] for s in steps.loop()}
    assert types[1] == "person" and types[2] == "LLM"
    assert types[3] == "ML" and types[4] == "ML" and types[5] == "code" and types[6] == "person"
    assert types[7] == "code" and types[8] == "code" and types[9] == "LLM" and types[10] == "person"


def test_unbuilt_steps_are_not_marked_built():
    by_n = {s["n"]: s for s in steps.loop()}
    # Honesty check: steps that use a mock fallback must not claim to be fully built.
    assert by_n[10]["status"] == "Built" and by_n[10]["type"] == "person"
    assert by_n[9]["status"] == "Partly built"  # real LLM with a mock fallback, actions only logged
    assert by_n[2]["status"] == "Partly built"  # real LLM with a mock fallback, not fully built
    assert by_n[3]["mock"] is True and by_n[4]["mock"] is True and by_n[7]["mock"] is True
    assert [s["step"] for s in steps.loop()] == [
        "Customer targets in", "Setup agent", "Optimizer", "Prediction model", "Safety gate",
        "Scientist reviews risky plans", "Make and measure", "Measurement check", "Diagnosis agent", "Release check",
    ]


def test_every_labeled_span_uses_a_valid_type():
    for name in steps._SPAN_LABELS:
        assert steps.span_labels(name)["step_type"] in steps.STEP_TYPES


def test_node_prefix_is_ignored_and_unknown_spans_get_no_label():
    assert steps.span_labels("node.policy_kernel") == steps.span_labels("policy_kernel")
    assert steps.span_labels("something.else") == {}


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", lambda name, *a, **k: provider.get_tracer(name))
    return exporter


def test_live_spans_carry_step_labels(spans):
    with telemetry.span("policy.check", candidate_id="C-1"):
        pass
    attrs = dict(spans.get_finished_spans()[0].attributes)
    assert attrs["step_type"] == "code" and attrs["step_n"] == 5 and attrs["is_mock"] is False


def test_explicit_attributes_win_over_labels(spans):
    with telemetry.span("policy.check", step_type="person"):
        pass
    assert dict(spans.get_finished_spans()[0].attributes)["step_type"] == "person"


def test_plan_in_mock_mode_labels_every_node_span_and_flags_the_mock(spans, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    CampaignOrchestrator(str(tmp_path / "cp.sqlite")).plan("CAMP-014", "t-labels")
    by_name = {s.name: dict(s.attributes) for s in spans.get_finished_spans()}
    for name in ("node.setup_agent", "node.optimizer", "node.prediction_model", "node.policy_kernel", "node.triage_and_hitl"):
        assert "step_type" in by_name[name], name
    assert by_name["node.setup_agent"]["step_type"] == "LLM" and by_name["node.setup_agent"]["step_n"] == 2
    assert by_name["node.setup_agent"]["is_mock"] is True  # no API key: the setup step is a plain lookup
    assert by_name["node.optimizer"]["step_type"] == "ML" and by_name["node.optimizer"]["step_n"] == 3 and by_name["node.optimizer"]["is_mock"] is True
    assert by_name["node.prediction_model"]["step_type"] == "ML" and by_name["node.prediction_model"]["step_n"] == 4
    assert by_name["presynthesis.review"]["step_type"] == "ML" and by_name["presynthesis.review"]["is_mock"] is True
