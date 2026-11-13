"""The pre-synthesis risk signals are a deterministic mock. Same recipe in, same signals out."""
from app import presynthesis


def test_demo_control_recipe_is_borderline_and_needs_review():
    s = presynthesis.risk_signals("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
    assert s["predicted_ductility_margin"] == 0.71 and s["ductility_label"] == "borderline"
    assert s["furnace_blast_radius"] == "high" and s["phase_stability"] == 0.97
    assert s["restricted_elements"] == []
    assert presynthesis.needs_review(s) is True


def test_ordinary_recipe_is_comfortable_and_skips_review():
    s = presynthesis.risk_signals("Nb40-Ti25-Cr20-Al15", "Arc-Melt")
    assert s["ductility_label"] == "comfortable" and s["furnace_blast_radius"] == "low"
    assert presynthesis.needs_review(s) is False


def test_lookup_ignores_element_order_and_processing_case():
    a = presynthesis.risk_signals("Al15-Cr15-Ti20-Nb50", "additive/anneal")
    assert a["predicted_ductility_margin"] == 0.71


def test_restricted_elements_are_real_not_mocked():
    s = presynthesis.risk_signals("Nb40-Ti25-Hf15-Al20", "Arc-Melt")
    assert s["restricted_elements"] == ["Hf"]
    assert presynthesis.needs_review(s) is True


def test_signals_are_labeled_as_a_mock_and_are_deterministic():
    one = presynthesis.risk_signals("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
    two = presynthesis.risk_signals("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
    assert one == two and "mock" in one["source"]


def test_review_reason_names_the_signals_and_the_timing():
    s = presynthesis.risk_signals("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
    reason = presynthesis.review_reason(s)
    assert "Run-071" in reason and "borderline" in reason
    assert "2.1% elongation" in reason and "3.0%" in reason and "minimum 2.4%" in reason
    assert "blast radius is high" in reason and "before any sample is made" in reason


def test_elongation_display_is_the_margin_scaled_to_the_baseline_and_does_not_change_the_decision():
    s = presynthesis.risk_signals("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
    assert s["predicted_elongation_pct"] == 2.1 and s["baseline_elongation_pct"] == 3.0 and s["min_elongation_pct"] == 2.4
    assert s["predicted_elongation_pct"] < s["min_elongation_pct"]  # same call as margin < 0.80
    ok = presynthesis.risk_signals("Nb40-Ti25-Cr20-Al15", "Arc-Melt")
    assert ok["predicted_elongation_pct"] == 2.8 and ok["predicted_elongation_pct"] >= ok["min_elongation_pct"]
