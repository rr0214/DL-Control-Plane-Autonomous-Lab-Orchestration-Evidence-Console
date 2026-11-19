"""S6: the case generator, the runner (mock path and a faked real path), the spend cap, and the CSV."""
import csv
import json
from types import SimpleNamespace

import pytest

from app import s6_export, s6_runner, synth_cases
from app.mcp_server import DIRECT_TOOLS

# ---- generator ----------------------------------------------------------------------------------

def test_thirty_cases_28_real_and_2_mock_with_unique_ids():
    cases = synth_cases.generate()
    assert len(cases) == 30 and len({c["case_id"] for c in cases}) == 30
    assert sum(c["mode"] == "real" for c in cases) == 28 and sum(c["mode"] == "mock" for c in cases) == 2


def test_generator_is_deterministic_and_the_committed_file_is_current():
    assert synth_cases.generate() == synth_cases.generate()
    assert json.loads(synth_cases.CASES_PATH.read_text(encoding="utf-8")) == json.loads(json.dumps(synth_cases.generate()))  # rerun synth_cases if this fails


def test_every_dimension_value_is_covered_at_least_three_times_except_the_rare_ones():
    cases = synth_cases.generate()
    for dim, values in {
        "targets": synth_cases.TARGETS,
        "history": synth_cases.HISTORIES,
        "scientist_action": ["approve", "revise", "reject", "none"],
        "release_attempt": ["release_with_reason", "release_short_note", "withhold", "none"],
    }.items():
        for v in values:
            n = sum(1 for c in cases if c["dims"][dim] == v)
            assert n >= (2 if v == "withhold" else 3), (dim, v, n)


def test_grid_cases_are_all_distinct_and_release_is_only_tried_after_an_approval():
    cases = synth_cases.generate()
    grid = [c for c in cases if c["kind"] == "grid"]
    assert len(grid) == 24 and len({tuple(c["dims"].values()) for c in grid}) == 24
    assert all(c["release"] is None for c in cases if c["dims"]["scientist_action"] != "approve")
    assert any(c["kind"] == "adversarial" and c["history_seed"] and "Ignore all previous" in c["history_seed"][0][4] for c in cases)


def test_target_values_are_inside_the_allowed_ranges():
    from app.targets import CustomerTargets

    for c in synth_cases.generate():
        CustomerTargets(**c["targets"])  # raises if out of range


# ---- runner: mock path --------------------------------------------------------------------------

def run(tmp_path, monkeypatch, *argv):
    monkeypatch.setenv("SDL_TRACING", "off")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "x.db"))
    return s6_runner.main(["--out", str(tmp_path), *argv])


def test_mock_batch_runs_every_case_and_writes_results_and_the_csv(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, monkeypatch, "--mock-only") == 0
    results = json.loads((tmp_path / "results.json").read_text())["results"]
    assert len(results) == 30 and all(r["error"] is None for r in results)
    assert all(r["llm_totals"]["calls"] == 0 for r in results)
    out = capsys.readouterr().out
    assert "logged cost: $0.0000" in out and "cache hits: 0 tokens read from cache" in out
    rows = list(csv.DictReader((tmp_path / "s6_cases.csv").open(encoding="utf-8-sig")))
    assert len(rows) == 30 and list(rows[0].keys()) == ["case_id", "inputs", "final_output", "phoenix_trace_url", "notes"]
    assert all(r["notes"] == "" and r["phoenix_trace_url"] == "" for r in rows)  # Phoenix off: blank link, empty notes
    assert "targets: 1200 C" in rows[0]["inputs"] and "status=" in rows[0]["final_output"]


def test_runner_never_touches_the_real_database(tmp_path, monkeypatch):
    real = tmp_path / "real.db"
    monkeypatch.setenv("SDL_DB_PATH", str(real))
    monkeypatch.setenv("SDL_TRACING", "off")
    s6_runner.main(["--out", str(tmp_path / "out"), "--mock-only", "--only", "S6-001,S6-002"])
    from app import db

    conn = db.connect(str(real))
    assert db.list_samples(conn, "CAMP-014") == []  # the cases wrote to their own throwaway databases
    conn.close()


def test_history_is_seeded_so_the_setup_agent_sees_it(tmp_path, monkeypatch):
    from app import db, history

    path = str(tmp_path / "h.db")
    conn = db.connect(path)
    s6_runner.seed_history(conn, synth_cases.HISTORIES["mixed"])
    lines = [history.format_line(r) for r in history.planner_history(conn, "CAMP-014")]
    assert any("Blast radius too high" in line and "quoted data" in line for line in lines)
    conn.close()


def test_real_mode_without_a_key_refuses_to_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr("app.config.anthropic_key", lambda: "")
    assert run(tmp_path, monkeypatch) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


# ---- runner: faked real path, spend cap -----------------------------------------------------------

class FakeClient:
    def __init__(self, cost_in=1_000_000):
        self.cost_in = cost_in
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls += 1
        block = SimpleNamespace(
            type="tool_use", id="t", name="submit_setup",
            input={"elements": [{"symbol": s, "min_pct": 0, "max_pct": 60} for s in ("Nb", "Ti", "Cr", "Al")], "routes": ["Arc-Melt"], "directions": []},
        )
        usage = SimpleNamespace(input_tokens=self.cost_in, output_tokens=0, cache_creation_input_tokens=0, cache_read_input_tokens=500)
        return SimpleNamespace(content=[block], usage=usage)


def test_spend_cap_stops_the_batch_before_the_next_case(tmp_path, monkeypatch, capsys):
    import anthropic

    fake = FakeClient(cost_in=400_000)  # about $1.20 per call; an approved case makes two calls (setup + diagnosis), a revised one makes one
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: fake)
    code = run(tmp_path, monkeypatch, "--only", "S6-001,S6-002,S6-003", "--max-usd", "3.0")
    assert code == 3
    data = json.loads((tmp_path / "results.json").read_text())
    assert [r["case_id"] for r in data["results"]] == ["S6-001", "S6-002"] and data["skipped"] == ["S6-003"]
    out = capsys.readouterr().out
    assert "STOPPED: spend reached the $3.00 cap" in out and "logged cost: $3.6" in out
    assert "cache hits: 1500 tokens read from cache" in out


def test_real_case_records_the_setup_pick_and_cost(tmp_path, monkeypatch):
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: FakeClient(cost_in=1000))
    run(tmp_path, monkeypatch, "--only", "S6-001")
    r = json.loads((tmp_path / "results.json").read_text())["results"][0]
    assert "setup=Claude" in r["final_output"] and "pick=Nb45-Ti25-Cr20-Al10" in r["final_output"]
    assert r["llm_totals"]["calls"] >= 1 and r["llm_totals"]["cost_usd"] > 0


def test_case_errors_are_recorded_as_error_rows(tmp_path, monkeypatch):
    class Broken:
        def post(self, *a, **k):
            return SimpleNamespace(status_code=500, text="server down", json=lambda: {})

    monkeypatch.setenv("SDL_TRACING", "off")
    res = s6_runner.run_case(Broken(), synth_cases.generate()[0], tmp_path, None)
    assert res["error"] and res["final_output"].startswith("ERROR:")


# ---- links and export -----------------------------------------------------------------------------

def test_trace_url_is_blank_without_phoenix_and_built_from_the_project_id_with_it():
    assert s6_runner.trace_url("http://localhost:6006", None, "abc") == ""
    assert s6_runner.trace_url("http://localhost:6006", "UHJvamVjdDox", "") == ""
    assert s6_runner.trace_url("http://localhost:6006/", "UHJvamVjdDox", "abc") == "http://localhost:6006/projects/UHJvamVjdDox/traces/abc"
    assert s6_runner.phoenix_project_id("sdl-s6", "http://127.0.0.1:9") is None  # nothing listening


def test_one_trace_per_case_covers_plan_review_and_release(tmp_path, monkeypatch):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", lambda name, *a, **k: provider.get_tracer(name))
    monkeypatch.setenv("SDL_TRACING", "off")
    run(tmp_path, monkeypatch, "--mock-only", "--only", "S6-001")
    res = json.loads((tmp_path / "results.json").read_text())["results"][0]
    names_in_trace = {s.name for s in exporter.get_finished_spans() if format(s.context.trace_id, "032x") == res["trace_id"]}
    assert {"s6.case", "campaign.plan", "scientist.review", "release.signoff"} <= names_in_trace
    assert {"node.setup_agent", "node.optimizer", "node.prediction_model", "node.policy_kernel", "node.diagnose_flagged"} <= names_in_trace


def test_csv_has_the_requested_columns_and_an_empty_notes_column(tmp_path):
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"results": [{"case_id": "S6-001", "mode": "real", "trace_id": "ab", "final_output": "status=complete", "trace_url": "http://x/p/1/traces/ab"}]}))
    out = s6_export.write_csv(results, tmp_path / "o.csv", synth_cases.CASES_PATH)
    row = next(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert row["phoenix_trace_url"] == "http://x/p/1/traces/ab" and row["notes"] == "" and "mode: real" in row["inputs"]
