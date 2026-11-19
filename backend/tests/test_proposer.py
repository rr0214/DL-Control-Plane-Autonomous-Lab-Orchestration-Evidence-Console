from app import optimizer, prediction_model, proposer
from app.mcp_server import DIRECT_TOOLS

HISTORY = [
    {"run_id": "Run-088", "composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt", "outcome": "Red"},
]


def direct_call(name, args):
    return DIRECT_TOOLS[name](**args), "direct"


def _has(rows, composition, processing):
    return any(r["composition"] == composition and r["processing"] == processing for r in rows)


def test_fixed_rows_are_both_probes_and_the_review_control():
    rows, calls = proposer.fixed_rows(direct_call)
    assert len(rows) == 3
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")  # restricted element probe
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Arc-Melt")         # Run-088 boundary probe
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Additive/Anneal")  # Yellow control
    assert {r["origin"] for r in rows} == {"boundary_probe", "yellow_control"}
    assert all(c["tool"] == "propose_alloy_ratios" for c in calls)


SPACE = {
    "elements": [{"symbol": s, "min_pct": 0, "max_pct": 60} for s in ("Nb", "Ti", "Cr", "Al")],
    "routes": ["Arc-Melt", "Additive/Anneal"],
}


def _pick_for(space, history=HISTORY):
    fixed, _ = proposer.fixed_rows(direct_call)
    out = DIRECT_TOOLS["propose_alloy_ratios"](search_space=space, n=6)
    scored = prediction_model.score(proposer.space_rows(out))
    return proposer.pick(scored, fixed, history), fixed


def test_pick_is_the_best_new_recipe_and_the_batch_keeps_probes_and_control():
    chosen, fixed = _pick_for(SPACE)
    assert chosen[0]["composition"] == "Nb45-Ti25-Cr20-Al10"  # Nb50 is the Run-088 repeat, so the next best leads
    assert chosen[0]["origin"] == "optimizer"
    rows = proposer.assemble(chosen, prediction_model.score(fixed))
    assert [r["candidate_id"] for r in rows] == ["C-1", "C-2", "C-3", "C-4"]
    assert _has(rows, "Nb40-Ti25-Hf15-Al20", "Additive/Anneal")
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Arc-Melt")
    assert _has(rows, "Nb50-Ti20-Cr15-Al15", "Additive/Anneal")


def test_a_pick_that_repeats_a_control_is_not_doubled():
    narrow = {"elements": [{"symbol": s, "min_pct": 15, "max_pct": 50} for s in ("Nb", "Ti", "Cr", "Al")], "routes": ["Arc-Melt"]}
    # Only the Run-088 repeat fits when the ranges are this tight and the other rows fall outside them.
    narrow["elements"][0]["min_pct"] = 50
    chosen, fixed = _pick_for(narrow)
    assert chosen[0]["composition"] == "Nb50-Ti20-Cr15-Al15"  # kept so the gate can block it
    rows = proposer.assemble(chosen, fixed)
    assert sum(1 for r in rows if r["composition"] == "Nb50-Ti20-Cr15-Al15" and r["processing"] == "Arc-Melt") == 1


def test_optimizer_stays_inside_the_search_space():
    space = {"elements": [{"symbol": s, "min_pct": 10, "max_pct": 30} for s in ("Nb", "Ti", "Cr", "Al")], "routes": ["Arc-Melt"]}
    assert optimizer.in_space(space)["candidates"] == []  # Nb is never between 10 and 30 in the table
    out = optimizer.in_space(SPACE)
    assert out["backend"] == "mock-optimizer-v1" and all(c["processing"] in SPACE["routes"] for c in out["candidates"])
    assert all("Si" not in c["composition"] and "Mo" not in c["composition"] for c in out["candidates"])  # not allowed elements


def test_prediction_model_scores_every_row_and_is_marked_mock():
    rows = prediction_model.score([{"composition": "Nb45-Ti25-Cr20-Al10", "processing": "Arc-Melt"}, {"composition": "Zr100", "processing": "Arc-Melt"}])
    assert rows[0]["expected_improvement"] == 0.90 and rows[0]["prediction_backend"] == "mock-prediction-v1"
    assert rows[1]["expected_improvement"] is None  # unknown composition: no guess
