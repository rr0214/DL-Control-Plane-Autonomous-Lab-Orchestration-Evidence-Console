"""S2: real planner pick is kept, usage is recorded, literature agent cites only what was retrieved.
The Anthropic client is faked; no network and no key are used."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config, literature, llm_usage, optimizer, proposer
from app.api import create_app
from app.mcp_server import DIRECT_TOOLS
from app.orchestrator import CampaignOrchestrator

HISTORY = [{"run_id": "Run-088", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "outcome": "Red"}]


def direct_call(name, args):
    return DIRECT_TOOLS[name](**args), "direct"


def block_text(text):
    return SimpleNamespace(type="text", text=text)


def block_tool(elements, processing, n=3):
    return SimpleNamespace(type="tool_use", id="tu1", name="propose_alloy_ratios", input={"elements": elements, "processing": processing, "n": n})


class FakeClient:
    """Plays back scripted responses. Each response is (content blocks, input tokens, output tokens)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content, tin, tout = self.script.pop(0)
        return SimpleNamespace(content=content, usage=SimpleNamespace(input_tokens=tin, output_tokens=tout))


def install(monkeypatch, client):
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: client)


# ---- planner ---------------------------------------------------------------------------------

def test_planner_pick_is_kept_not_replaced_by_the_mock(monkeypatch):
    fake = FakeClient([([block_tool(["Nb", "Ti", "Cr", "Al"], "Arc-Melt")], 900, 80), ([block_text("Done.")], 1000, 10)])
    install(monkeypatch, fake)
    usage = []
    rows, mode, note, calls = proposer.propose("goal", HISTORY, direct_call, usage=usage)
    assert mode == "anthropic"  # before S2 this fell back to mock
    assert rows[0]["origin"] == "llm" and rows[0]["candidate_id"] == "C-1"
    assert rows[0]["composition"] == "Nb45-Ti25-Cr20-Al10"  # top new recipe, not the Run-088 repeat
    assert len(rows) == 4
    assert note.startswith("Claude (claude-sonnet-5-5) proposed Nb45-Ti25-Cr20-Al10 via Arc-Melt")
    assert [u["agent"] for u in usage] == ["planner", "planner"]


def test_planner_repeat_of_a_failed_run_is_kept_so_the_gate_can_block_it(monkeypatch):
    fake = FakeClient([([block_tool(["Nb", "Ti", "Cr", "Al"], "Arc-Melt", n=1)], 500, 50), ([block_text("ok")], 500, 5)])
    install(monkeypatch, fake)
    rows, mode, note, _ = proposer.propose("goal", HISTORY, direct_call)
    assert mode == "anthropic"
    assert rows[0]["origin"] == "llm" and rows[0]["composition"] == "Nb50-Ti20-Cr15-Al15"
    # the Run-088 probe is not doubled
    assert sum(1 for r in rows if r["composition"] == "Nb50-Ti20-Cr15-Al15" and r["processing"] == "Arc-Melt") == 1


def test_planner_never_proposes_hafnium_from_the_new_table():
    assert all("Hf" not in r["composition"] for r in optimizer.SURROGATE_TABLE[2:])
    for r in optimizer.SURROGATE_TABLE:
        total = sum(float(x) for x in __import__("re").findall(r"\d+(?:\.\d+)?", r["composition"]))
        assert total == 100


# ---- usage and cost ---------------------------------------------------------------------------

def test_cost_uses_the_price_table_and_unknown_models_have_no_cost():
    assert llm_usage.cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == 18.0
    assert llm_usage.cost_usd("some-future-model", 10, 10) is None


def test_call_records_tokens_latency_prompt_version_and_commit():
    fake = FakeClient([([block_text("hi")], 1200, 300)])
    _, rec = llm_usage.call(fake, agent="planner", prompt_version="planner-v2", model="claude-sonnet-5-5", max_tokens=10, messages=[])
    assert rec["input_tokens"] == 1200 and rec["output_tokens"] == 300
    assert rec["cost_usd"] == round((1200 * 3 + 300 * 15) / 1e6, 6)
    assert rec["prompt_version"] == "planner-v2" and rec["git_commit"] and rec["latency_ms"] >= 0


def test_totals_cost_is_none_if_any_call_is_unpriced():
    good = {"model": "claude-sonnet-5-5", "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.1, "latency_ms": 5.0}
    bad = dict(good, model="x", cost_usd=None)
    assert llm_usage.totals([good, good])["cost_usd"] == 0.2
    assert llm_usage.totals([good, bad])["cost_usd"] is None
    assert llm_usage.totals([])["calls"] == 0


def test_agent_model_setting_order(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("SDL_MODEL_PLANNER", raising=False)
    assert config.agent_model("planner") == "claude-sonnet-5-5"
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
    assert config.agent_model("planner") == "claude-haiku-5-5"
    monkeypatch.setenv("SDL_MODEL_PLANNER", "claude-opus-5-5")
    assert config.agent_model("planner") == "claude-opus-5-5"
    assert config.agent_model("literature") == "claude-haiku-5-5"
    with pytest.raises(ValueError):
        config.agent_model("nobody")


# ---- literature agent -------------------------------------------------------------------------

def _first_ref_id():
    return DIRECT_TOOLS["search_calphad_literature"](elements=["Nb", "Ti", "Cr", "Al"], limit=3)["results"][0]["id"]


def test_literature_agent_keeps_only_retrieved_citations(monkeypatch):
    rid = _first_ref_id()
    reply = json.dumps(
        {
            "directions": [
                {"direction": "Try Si for oxidation resistance.", "cited_ids": [rid]},
                {"direction": "Invented citation only.", "cited_ids": ["made-up-2099"]},
                {"direction": "Half valid.", "cited_ids": ["made-up-2099", rid]},
            ]
        }
    )
    install(monkeypatch, FakeClient([([block_text(reply)], 800, 120)]))
    out = literature.run("goal", {"service_temp_c": 1200, "min_yield_strength_mpa": 600, "max_hafnium_at_pct": 0.0}, ["Nb", "Ti", "Cr", "Al"], direct_call)
    assert out["mode"] == "anthropic"
    assert [d["direction"] for d in out["directions"]] == ["Try Si for oxidation resistance.", "Half valid."]
    assert out["directions"][1]["cited_ids"] == [rid]
    assert out["usage"][0]["agent"] == "literature"


def test_literature_agent_without_key_is_a_labeled_plain_lookup(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    out = literature.run("goal", None, ["Nb", "Ti"], direct_call)
    assert out["mode"] == "mock" and out["directions"] == [] and out["references"] and out["usage"] == []
    assert "plain lookup" in out["note"]


def test_literature_agent_survives_a_bad_reply_and_a_failed_call(monkeypatch):
    install(monkeypatch, FakeClient([([block_text("not json at all")], 10, 5)]))
    assert literature.run("g", None, ["Nb"], direct_call)["directions"] == []

    def boom(**k):
        raise RuntimeError("down")

    broken = FakeClient([])
    broken.messages = SimpleNamespace(create=boom)
    install(monkeypatch, broken)
    out = literature.run("g", None, ["Nb"], direct_call)
    assert out["mode"] == "mock" and "failed" in out["note"] and out["references"]


# ---- end to end -------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return lambda: TestClient(create_app(CampaignOrchestrator(str(tmp_path / "cp.sqlite"))))


def test_full_plan_with_fake_llm_records_usage_and_shows_in_summary(client, monkeypatch):
    rid = _first_ref_id()
    install(
        monkeypatch,
        FakeClient(
            [
                ([block_text(json.dumps({"directions": [{"direction": "Si helps.", "cited_ids": [rid]}]}))], 700, 100),
                ([block_tool(["Nb", "Ti", "Cr", "Al"], "Arc-Melt")], 900, 80),
                ([block_text("Done.")], 1000, 10),
            ]
        ),
    )
    c = client()
    body = c.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-real"}).json()
    assert body["llm_mode"] == "anthropic" and body["literature_mode"] == "anthropic"
    assert body["directions"][0]["direction"] == "Si helps."
    assert body["llm_totals"]["calls"] == 3 and body["llm_totals"]["input_tokens"] == 2600
    assert body["llm_totals"]["cost_usd"] > 0
    assert any("Claude (claude-sonnet-5-5) proposed" in n for n in body["notes"])
    assert body["pending"]["sample_id"] == "S-C-4"  # planner pick C-1, probes C-2/C-3, Yellow control C-4

    usage = c.get("/api/usage/summary").json()
    assert usage["real_plans"] == 1 and usage["avg_cost_usd"] > 0 and "Verify" in usage["price_note"]
    assert usage["plans"][0]["calls"] == 3


def test_mock_plan_reports_zero_llm_calls(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    c = client()
    body = c.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": "t-mock"}).json()
    assert body["llm_totals"]["calls"] == 0 and body["llm_totals"]["cost_usd"] is None
    usage = c.get("/api/usage/summary").json()
    assert usage["real_plans"] == 0 and usage["mock_plans"] == 1 and usage["avg_cost_usd"] is None


def test_llm_call_span_carries_tokens_cost_prompt_version_and_commit(monkeypatch):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", lambda name, *a, **k: provider.get_tracer(name))
    llm_usage.call(FakeClient([([block_text("x")], 100, 20)]), agent="planner", prompt_version="planner-v2", model="claude-sonnet-5-5", max_tokens=5, messages=[])
    attrs = dict(exporter.get_finished_spans()[0].attributes)
    assert attrs["llm.token_count.prompt"] == 100 and attrs["llm.token_count.completion"] == 20
    assert attrs["llm.model_name"] == "claude-sonnet-5-5" and attrs["prompt_version"] == "planner-v2"
    assert attrs["git_commit"] and "llm.cost_usd" in attrs and "llm.latency_ms" in attrs
    assert attrs["step_type"] == "LLM" and attrs["step_n"] == 3
    assert attrs["openinference.span.kind"] == "LLM"
