import pytest

from app.chemistry import parse
from app.orchestrator import CampaignOrchestrator


@pytest.fixture
def orch(tmp_path, monkeypatch):
    # Force mock mode and an isolated database, regardless of the developer's .env.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))
    return CampaignOrchestrator(str(tmp_path / "checkpoints.sqlite"))


def test_plan_pauses_on_yellow_sample(orch):
    out = orch.plan("CAMP-014", "thread-1")
    assert out["status"] == "paused"
    assert out["pending"]["status"] == "Yellow"
    assert "0.71" in out["pending"]["reason"]
    assert "not composition novelty" in out["pending"]["reason"]


def test_review_resumes_and_gate_blocks_both_test_routes(orch):
    orch.plan("CAMP-014", "thread-2")
    done = orch.review("thread-2", "approve", "Phase looks right, no rescan needed")

    assert done["status"] == "complete"
    assert done["llm_mode"] == "mock"
    assert done["triage"][0]["decision"] == "approve"
    assert done["triage"][0]["intuition_note"] == "Phase looks right, no rescan needed"

    blocked = {v["rule"] for v in done["verdicts"] if not v["allowed"]}
    assert blocked == {"DUPLICATE_CONDITION", "RESTRICTED_ELEMENT"}

    allowed = [c for c, v in zip(done["candidates"], done["verdicts"]) if v["allowed"]]
    assert len(allowed) == 1
    assert allowed[0]["processing"] == "Additive/Anneal"


def test_every_ratio_comes_from_optimizer_and_sums_to_100(orch):
    orch.plan("CAMP-014", "thread-3")
    done = orch.review("thread-3", "kill")
    assert len(done["candidates"]) == 3
    for c in done["candidates"]:
        assert c["source"] == "bayesian_optimizer"
        assert sum(parse(c["composition"]).values()) == 100
