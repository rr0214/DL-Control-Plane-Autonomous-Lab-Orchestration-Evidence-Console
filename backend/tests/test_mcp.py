import pytest

from app import db
from app.mcp_server import DIRECT_TOOLS, ToolGateway, check_negative_runs, propose_alloy_ratios, search_calphad_literature, server


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_DB_PATH", str(tmp_path / "sdl.db"))


def test_propose_alloy_ratios_returns_numeric_ratios_summing_to_100():
    out = propose_alloy_ratios(["Nb", "Ti", "Cr", "Al"], "Arc-Melt", n=1)
    assert out["candidates"]
    from app.chemistry import parse

    for c in out["candidates"]:
        assert sum(parse(c["composition"]).values()) == 100


def test_check_negative_runs_finds_run_088_on_exact_route():
    out = check_negative_runs("Nb50-Ti20-Cr15-Al15", "Arc-Melt")
    assert [m["run_id"] for m in out["exact_matches"]] == ["Run-088"]
    assert out["exact_matches"][0]["outcome"] == "Red"


def test_check_negative_runs_reports_same_composition_on_other_route():
    out = check_negative_runs("Nb50-Ti20-Cr15-Al15", "Additive/Anneal")
    assert out["exact_matches"] == []
    assert [r["run_id"] for r in out["same_composition_other_routes"]] == ["Run-088"]


def test_search_literature_returns_doi_citations():
    out = search_calphad_literature(elements=["Nb", "Ti"], limit=10)
    assert out["results"]
    for item in out["results"]:
        assert item["doi_url"] == f"https://doi.org/{item['doi']}"
        assert item["doi"].startswith("10.")
    assert any(item["doi"] == "10.3390/ma17184579" for item in out["results"])


def test_fastmcp_server_exposes_the_three_contract_tools():
    assert server is not None, "mcp package must be installed"
    import asyncio

    names = asyncio.run(_list_names())
    assert names == {"propose_alloy_ratios", "check_negative_runs", "search_calphad_literature"}


async def _list_names():
    from mcp.shared.memory import create_connected_server_and_client_session

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        await session.initialize()
        return {t.name for t in (await session.list_tools()).tools}


def test_gateway_uses_fastmcp_transport_by_default():
    gw = ToolGateway()
    assert gw.mode == "fastmcp"
    result, transport = gw.call("check_negative_runs", {"composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt"})
    assert transport == "fastmcp"
    assert result["exact_matches"][0]["run_id"] == "Run-088"


def test_gateway_direct_mode_gives_the_same_answer(monkeypatch):
    monkeypatch.setenv("SDL_MCP_MODE", "direct")
    gw = ToolGateway()
    assert gw.mode == "direct"
    result, transport = gw.call("check_negative_runs", {"composition": "Nb50-Ti20-Cr15-Al15", "processing": "Arc-Melt"})
    assert transport == "direct"
    assert result == DIRECT_TOOLS["check_negative_runs"](composition="Nb50-Ti20-Cr15-Al15", processing="Arc-Melt")


def test_gateway_rejects_unknown_tool():
    with pytest.raises(KeyError):
        ToolGateway().call("rm_rf", {})
