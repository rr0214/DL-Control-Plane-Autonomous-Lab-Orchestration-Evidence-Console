"""Every LLM span and key decision span records its real input and output as readable text."""
import json

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import diagnosis, setup_agent
from app.api import create_app
from app.orchestrator import CampaignOrchestrator
from test_llm_s2 import FakeClient, HISTORY, _first_ref_id, block_setup, block_text, direct_call, install


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", lambda name, *a, **k: provider.get_tracer(name))
    return lambda name: [dict(s.attributes) for s in exporter.get_finished_spans() if s.name == name]


def test_llm_setup_span_shows_prompt_answer_search_space_and_cited_directions(spans, monkeypatch):
    rid = _first_ref_id()
    install(monkeypatch, FakeClient([([block_setup(directions=[{"direction": "Si helps oxidation.", "cited_ids": [rid]}, {"direction": "Made up.", "cited_ids": ["NOPE"]}])], 900, 80)]))
    setup_agent.run("Find a hot-section alloy", None, HISTORY, ["Nb", "Ti", "Cr", "Al"], direct_call)
    a = spans("llm.setup")[0]
    assert "Campaign goal: Find a hot-section alloy" in a["input.value"] and rid in a["input.value"]  # the prompt as the model read it
    assert "submit_setup" in a["output.value"] and "Nb" in a["output.value"]  # the raw answer
    assert a["setup.search_space"].startswith("Nb 0 to 60%") and a["setup.routes"] == "Arc-Melt"
    assert f"Si helps oxidation.  [cites {rid}]" in a["setup.directions"]
    assert "Made up." not in a["setup.directions"] and a["setup.directions_dropped_uncited"] == 1
    assert a["llm.system_prompt"]


def test_llm_diagnosis_span_shows_action_cause_and_reason(spans, monkeypatch):
    reply = '{"action": "re-measure", "cause": "instrument", "reason": "One flag only, so repeat the scan."}'
    install(monkeypatch, FakeClient([([block_text(reply)], 300, 40)]))
    diagnosis.propose({"sample_id": "S-1", "composition": "Nb45-Ti25-Cr20-Al10", "processing": "Arc-Melt", "status": "Yellow", "measurement_check": {"flags": ["composition_match"]}}, [])
    a = spans("llm.diagnosis")[0]
    assert a["input.value"] and a["output.value"] == reply
    assert (a["diagnosis.proposed_action"], a["diagnosis.cause"]) == ("re-measure", "instrument")
    assert a["diagnosis.reason"] == "One flag only, so repeat the scan." and a["diagnosis.parsed"] is True


def test_failed_llm_call_still_shows_what_was_sent(spans, monkeypatch):
    from types import SimpleNamespace

    def boom(**k):
        raise RuntimeError("HTTP 400")

    client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    install(monkeypatch, client)
    setup_agent.run("goal", None, HISTORY, ["Nb"], direct_call)
    assert all("Campaign goal" in a["input.value"] for a in spans("llm.setup")) and len(spans("llm.setup")) == 2


def test_decision_spans_record_input_and_output_across_a_full_loop(spans, monkeypatch, tmp_path):
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    rid = _first_ref_id()
    install(monkeypatch, FakeClient([([block_setup(directions=[{"direction": "Si helps.", "cited_ids": [rid]}])], 1700, 180), ([block_text('{"action": "hold", "cause": "material", "reason": "Disagrees with similar runs."}')], 500, 30)]))
    c = TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))
    plan = c.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-io"}).json()
    sid = plan["pending"]["sample_id"]
    c.post(f"/api/samples/{sid}/review", json={"decision": "approve", "note": "Margin is acceptable"}, headers={"X-Role": "Scientist (PI)"})
    c.post(f"/api/samples/{sid}/release", json={"decision": "withhold", "note": "Not convincing yet"}, headers={"X-Role": "Scientist (PI)"})

    for name in ("node.setup_agent", "node.optimizer", "node.prediction_model", "prediction.score", "policy.check",
                 "measure.sample", "measurement.check", "scientist.review", "campaign.plan", "release.signoff", "mcp.propose_alloy_ratios"):
        found = spans(name)
        assert found, f"no {name} span"
        for a in found:
            assert a.get("input.value") or a.get("output.value"), f"{name} has no readable input or output"
    # a few exact reads
    assert "Nb" in spans("node.optimizer")[0]["input.value"] and "Optimizer ratios" in spans("node.optimizer")[0]["output.value"]
    assert "Picked to lead the batch" in spans("node.prediction_model")[0]["output.value"]
    gate = spans("policy.check")
    assert all(a["input.value"] and a["output.value"].startswith(("Allowed", "Blocked")) for a in gate)
    assert any("Blocked by rule RESTRICTED_ELEMENT" in a["output.value"] for a in gate)
    chk = spans("measurement.check")[0]
    assert "hardness" in chk["input.value"] and "composition_match" in chk["output.value"] and "Severity" in chk["output.value"]
    rel = spans("release.signoff")[0]
    assert "Not convincing yet" in rel["input.value"] and rel["output.value"].startswith("Recorded: withhold")
    assert "setup_mode: anthropic" in spans("node.setup_agent")[0]["output.value"]
    assert spans("action.gate"), "the Yellow review sample should reach the action gate"
    for a in spans("action.gate"):
        assert "Proposal:" in a["input.value"] and "final action" in a["output.value"]
