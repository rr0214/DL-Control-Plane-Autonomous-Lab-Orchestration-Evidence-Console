from app import proposer

HISTORY = [
    {"run_id": "Run-088", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "outcome": "Red"},
]


def _has(rows, composition, processing):
    return any(r["composition"] == composition and r["processing"] == processing for r in rows)


def test_mock_mode_includes_both_boundary_probes(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    rows, mode, note = proposer.propose("goal", HISTORY)
    assert mode == "mock"
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")  # restricted element probe
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Arc-Melt")         # Run-088 boundary probe
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Additive/Anneal")  # allowed control


def test_real_mode_appends_probes_and_drops_llm_duplicates(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    llm_rows = [
        {"composition": "Nb45-Ti25-Cr15-Al15", "processing": "Additive/Anneal", "expected_improvement": 0.7, "origin": "llm"},
        # Duplicates the Run-088 probe, so it must be dropped rather than doubled.
        {"composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "expected_improvement": 0.9, "origin": "llm"},
    ]
    monkeypatch.setattr(proposer, "_propose_anthropic", lambda *a, **k: (llm_rows, 2))

    rows, mode, note = proposer.propose("goal", HISTORY)
    assert mode == "anthropic"
    assert len(rows) == 3  # one novel LLM candidate + two probes
    assert [r["candidate_id"] for r in rows] == ["C-1", "C-2", "C-3"]
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Arc-Melt")
    assert sum(1 for r in rows if r["composition"] == "Nb50-Ti20-Cr15-Al15") == 1
    assert "boundary probes appended" in note


def test_llm_failure_falls_back_to_mock_with_probes(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(proposer, "_propose_anthropic", boom)
    rows, mode, note = proposer.propose("goal", HISTORY)
    assert mode == "mock"
    assert "used mock plan" in note
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")
