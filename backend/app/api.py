"""FastAPI surface for the SDL Control Plane."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, seed_camp014
from .mcp_server import gateway
from .orchestrator import CampaignOrchestrator

KNOWN_CAMPAIGNS = {"CAMP-014"}


class PlanRequest(BaseModel):
    campaign_id: str = "CAMP-014"
    thread_id: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "rescan", "kill"]
    note: str = Field(default="", max_length=280)


def _persist(conn, thread_id: str, campaign_id: str, out: dict) -> None:
    db.save_plan(conn, thread_id, campaign_id, out)
    for record in out["triage"]:
        db.save_sample(conn, thread_id, campaign_id, record)
    if out["status"] == "paused" and out["pending"]:
        db.save_sample(conn, thread_id, campaign_id, out["pending"])


def _with_trace(thread_id: str, out: dict) -> dict:
    trace = seed_camp014.build_trace(
        thread_id,
        out["llm_mode"] or "mock",
        out["candidates"],
        out["verdicts"],
        out["triage"],
        out.get("tool_calls", []),
    )
    return dict(out, trace=trace, mcp_mode=gateway.mode)


def create_app(orchestrator: CampaignOrchestrator | None = None) -> FastAPI:
    app = FastAPI(title="SDL Control Plane API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.orchestrator = orchestrator

    def orch() -> CampaignOrchestrator:
        # Built on first use so importing the module does not touch the database.
        if app.state.orchestrator is None:
            app.state.orchestrator = CampaignOrchestrator()
        return app.state.orchestrator

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "mcp_mode": gateway.mode}

    @app.get("/api/campaigns/{campaign_id}")
    def get_campaign(campaign_id: str) -> dict:
        if campaign_id not in KNOWN_CAMPAIGNS:
            raise HTTPException(404, f"Unknown campaign {campaign_id}")
        conn = db.connect()
        try:
            campaign = db.get_campaign(conn, campaign_id)
            live = []
            for sample in db.list_samples(conn, campaign_id):
                sample["recorded_at"] = sample["updated_at"]
                live.append(dict(sample, receipt=seed_camp014.make_receipt(sample)))
            plans = db.list_plans(conn, campaign_id)
        finally:
            conn.close()
        literature, _ = gateway.call("search_calphad_literature", {"elements": ["Nb", "Ti", "Cr", "Al"], "limit": 3})
        return {
            "campaign": campaign,
            "rbac": seed_camp014.RBAC,
            "seed_samples": seed_camp014.SEED_SAMPLES,
            "live_samples": live,
            "plans": plans,
            "seed_trace": seed_camp014.SEED_TRACE,
            "literature": literature["results"],
            "mcp_mode": gateway.mode,
        }

    @app.post("/api/campaigns/plan")
    def plan(body: PlanRequest) -> dict:
        if body.campaign_id not in KNOWN_CAMPAIGNS:
            raise HTTPException(404, f"Unknown campaign {body.campaign_id}")
        thread_id = body.thread_id or f"plan-{uuid.uuid4().hex[:12]}"
        conn = db.connect()
        try:
            if conn.execute("SELECT 1 FROM plans WHERE thread_id = ?", (thread_id,)).fetchone():
                raise HTTPException(409, f"Thread {thread_id} already exists")
            out = orch().plan(body.campaign_id, thread_id)
            _persist(conn, thread_id, body.campaign_id, out)
        finally:
            conn.close()
        return _with_trace(thread_id, out)

    @app.post("/api/samples/{sample_id}/review")
    def review(
        sample_id: str,
        body: ReviewRequest,
        x_role: str = Header(default="Scientist (PI)"),
    ) -> dict:
        conn = db.connect()
        try:
            sample = db.get_sample(conn, sample_id)
            if sample is None:
                raise HTTPException(404, f"Unknown sample {sample_id}")
            if sample["decision"] is not None:
                raise HTTPException(409, f"{sample_id} already decided: {sample['decision']}")

            role = next((r for r in seed_camp014.RBAC["roles"] if r["role"] == x_role), None)
            needed = seed_camp014.RBAC["decision_permissions"][body.decision]
            if role is None or needed not in role["permissions"]:
                raise HTTPException(403, f"Role '{x_role}' may not '{body.decision}' samples")

            try:
                out = orch().review(sample["thread_id"], body.decision, body.note)
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(409, f"Could not resume thread: {exc}") from exc
            _persist(conn, sample["thread_id"], sample["campaign_id"], out)
        finally:
            conn.close()
        return _with_trace(sample["thread_id"], out)

    @app.post("/api/demo/reset")
    def reset_demo(
        campaign_id: str = "CAMP-014",
        x_role: str = Header(default="Scientist (PI)"),
    ) -> dict:
        """Clears plans, samples, and checkpoints for one campaign. Seed runs and campaigns are kept."""
        if campaign_id not in KNOWN_CAMPAIGNS:
            raise HTTPException(404, f"Unknown campaign {campaign_id}")
        role = next((r for r in seed_camp014.RBAC["roles"] if r["role"] == x_role), None)
        if role is None or "approve" not in role["permissions"]:
            raise HTTPException(403, f"Role '{x_role}' may not reset the demo")
        conn = db.connect()
        try:
            thread_ids = db.clear_campaign_lineage(conn, campaign_id)
        finally:
            conn.close()
        orch().forget_threads(thread_ids)
        return {"status": "reset", "campaign_id": campaign_id, "threads_cleared": len(thread_ids)}

    return app


app = create_app()
