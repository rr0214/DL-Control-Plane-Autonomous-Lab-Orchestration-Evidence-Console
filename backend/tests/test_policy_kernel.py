from app.policy_kernel import check

HISTORY = [
    {"run_id": "Run-088", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "outcome": "Red"},
]


def cand(cid: str, composition: str, processing: str) -> dict:
    return {"candidate_id": cid, "composition": composition, "processing": processing}


def test_blocks_exact_run_088_boundary():
    v = check(cand("C-1", "Nb50-Ti20-Cr15-Al15", "Arc-Melt"), HISTORY)
    assert not v.allowed
    assert v.rule == "DUPLICATE_CONDITION"
    assert "Run-088" in v.reason


def test_allows_same_composition_with_new_processing():
    v = check(cand("C-3", "Nb50-Ti20-Cr15-Al15", "Additive/Anneal"), HISTORY)
    assert v.allowed
    assert v.rule is None


def test_blocks_restricted_hf():
    v = check(cand("C-2", "Nb40-Ti25-Hf15-Al20", "Additive/Anneal"), HISTORY)
    assert not v.allowed
    assert v.rule == "RESTRICTED_ELEMENT"


def test_duplicate_match_ignores_processing_case():
    v = check(cand("C-4", "Nb50-Ti20-Cr15-Al15", "arc-melt"), HISTORY)
    assert v.rule == "DUPLICATE_CONDITION"


def test_gate_latency_under_50ms():
    v = check(cand("C-9", "Nb50-Ti20-Cr15-Al15", "Arc-Melt"), HISTORY)
    assert v.latency_ms < 50
