from app import proposer
from app.mcp_server import DIRECT_TOOLS

HISTORY = [
    {"run_id": "Run-088", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "outcome": "Red"},
]


def direct_call(name, args):
    return DIRECT_TOOLS[name](**args), "direct"


def _has(rows, composition, processing):
    return any(r["composition"] == composition and r["processing"] == processing for r in rows)


def test_mock_mode_includes_both_probes_and_yellow_control(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    rows, mode, note, calls = proposer.propose("goal", HISTORY, direct_call)
    assert mode == "mock"
    assert len(rows) == 3
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")  # restricted element probe
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Arc-Melt")         # Run-088 boundary probe
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Additive/Anneal")  # Yellow control
    assert {r["origin"] for r in rows} == {"boundary_probe", "yellow_control"}
    assert all(c["tool"] == "propose_alloy_ratios" for c in calls)


def test_real_mode_appends_probes_and_control_and_drops_llm_duplicates(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    llm_rows = [
        {"composition": "Nb45-Ti25-Cr15-Al15", "processing": "Additive/Anneal", "expected_improvement": 0.7, "origin": "llm"},
        # Duplicates the Run-088 probe, so it must be dropped rather than doubled.
        {"composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "expected_improvement": 0.9, "origin": "llm"},
    ]
    monkeypatch.setattr(proposer, "_propose_anthropic", lambda *a, **k: (llm_rows, 1))

    rows, mode, note, calls = proposer.propose("goal", HISTORY, direct_call)
    assert mode == "anthropic"
    assert len(rows) == 4  # one novel LLM candidate + Hf probe + Run-088 probe + Yellow control
    assert [r["candidate_id"] for r in rows] == ["C-1", "C-2", "C-3", "C-4"]
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Arc-Melt")
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Additive/Anneal")  # Yellow control always present
    assert sum(1 for r in rows if r["composition"] == "Nb50-Ti20-Cr15-Al15" and r["processing"] == "Arc-Melt") == 1
    assert "Yellow control appended" in note


def test_llm_failure_falls_back_to_mock_with_probes_and_control(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(proposer, "_propose_anthropic", boom)
    rows, mode, note, calls = proposer.propose("goal", HISTORY, direct_call)
    assert mode == "mock"
    assert "used mock plan" in note
    assert len(rows) == 3
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
