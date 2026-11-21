"""FastAPI surface for the SDL Control Plane."""
from __future__ import annotations

import hmac
import uuid
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from . import config, db, llm_usage, release, run_evals, seed_camp014, steps, telemetry
from .mcp_server import gateway
from .orchestrator import CampaignOrchestrator
from .targets import CustomerTargets

KNOWN_CAMPAIGNS = {"CAMP-014"}


class PlanRequest(BaseModel):
    campaign_id: str = "CAMP-014"
    thread_id: str | None = None
    targets: CustomerTargets | None = None  # customer target properties; the campaign's own are used when omitted
    # Test cases only: skip the setup agent and use this search space. The safety gate still checks every candidate.
    forced_search_space: dict | None = None


class ReleaseRequest(BaseModel):
    decision: Literal["release", "withhold"]
    note: str = Field(default="", max_length=280)


class ReviewRequest(BaseModel):
    decision: Literal["approve", "revise", "reject"]
    note: str = Field(default="", max_length=280)


def _persist(conn, thread_id: str, campaign_id: str, out: dict) -> None:
    db.save_plan(conn, thread_id, campaign_id, out)
    for record in out["triage"]:
        db.save_sample(conn, thread_id, campaign_id, record)
        if record.get("diagnosis"):
            db.save_action(conn, thread_id, campaign_id, record["sample_id"], record["diagnosis"])
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


OPEN_PATHS = {"/health"}  # the platform health check needs no password


class AccessPassword(BaseHTTPMiddleware):
    """When SDL_ACCESS_PASSWORD is set, every route except /health needs a matching X-Access-Password header.
    Unset (local use), nothing is checked. CORS preflights pass so the browser can ask before sending the header."""

    async def dispatch(self, request, call_next):
        expected = config.access_password()
        if expected and request.method != "OPTIONS" and request.url.path not in OPEN_PATHS:
            given = request.headers.get("x-access-password", "")
            if not hmac.compare_digest(given.encode(), expected.encode()):
                return JSONResponse({"detail": "Access password required"}, status_code=401)
        return await call_next(request)


def create_app(orchestrator: CampaignOrchestrator | None = None) -> FastAPI:
    app = FastAPI(title="SDL Control Plane API", version="0.5.0")
    # Added before CORS so CORS wraps it: a 401 still carries CORS headers and the browser can read it.
    app.add_middleware(AccessPassword)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins(),  # SDL_ALLOWED_ORIGINS, comma separated; localhost by default
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.orchestrator = orchestrator
    telemetry.init_tracing()  # no-op if SDL_TRACING=off or Phoenix is not running

    def orch() -> CampaignOrchestrator:
        # Built on first use so importing the module does not touch the database.
        if app.state.orchestrator is None:
            app.state.orchestrator = CampaignOrchestrator()
        return app.state.orchestrator

    @app.get("/health")
    def platform_health() -> dict:
        """Liveness for the hosting platform. Open even when a password is set; reports nothing else."""
        return {"status": "ok"}

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "mcp_mode": gateway.mode,
            "tracing": telemetry.is_enabled(),
            "phoenix_url": telemetry.PHOENIX_UI_URL,
        }

    @app.get("/api/loop")
    def loop() -> dict:
        """The 11-step target loop with each step's type (LLM, ML, code, person) and build status."""
        return {"steps": steps.loop()}

    @app.get("/api/usage/summary")
    def usage_summary() -> dict:
        """Cost and latency of real LLM calls, per plan and averaged. Mock plans make no calls and cost nothing."""
        conn = db.connect()
        try:
            plans = db.plan_usage(conn, "CAMP-014")
        finally:
            conn.close()
        rows = [
            {"thread_id": p["thread_id"], "llm_mode": p["llm_mode"], "created_at": p["created_at"], **llm_usage.totals(p["records"])}
            for p in plans
        ]
        real = [r for r in rows if r["calls"] > 0]
        priced = [r for r in real if r["cost_usd"] is not None]
        return {
            "plans": rows[:20],
            "real_plans": len(real),
            "mock_plans": len(rows) - len(real),
            "avg_cost_usd": round(sum(r["cost_usd"] for r in priced) / len(priced), 6) if priced else None,
            "avg_latency_ms": round(sum(r["latency_ms"] for r in real) / len(real), 1) if real else None,
            "prices_usd_per_mtok": llm_usage.PRICES_USD_PER_MTOK,
            "price_note": llm_usage.PRICE_NOTE,
        }

    @app.get("/api/evals/summary")
    def evals_summary() -> dict:
        """Read-only. Scores the golden dataset against the real gate and review code. No writes, no Phoenix needed."""
        return run_evals.summary()

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
            actions = db.list_actions(conn, campaign_id)
            releases = db.list_releases(conn, campaign_id)
        finally:
            conn.close()
        literature, _ = gateway.call("search_calphad_literature", {"elements": ["Nb", "Ti", "Cr", "Al"], "limit": 3})
        return {
            "campaign": campaign,
            "rbac": seed_camp014.RBAC,
            "seed_samples": seed_camp014.SEED_SAMPLES,
            "live_samples": live,
            "plans": plans,
            "actions": actions,
            "releases": releases,
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
            out = orch().plan(body.campaign_id, thread_id, body.targets.model_dump() if body.targets else None, body.forced_search_space)
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

            # A run can pause more than once (a risky pick, then the review test case). The decision must be for the
            # sample the thread is waiting on now, or it would be applied to a different recipe.
            waiting = orch().pending(sample["thread_id"])
            if waiting is None or waiting.get("sample_id") != sample_id:
                raise HTTPException(409, f"{sample_id} is not the sample waiting for review" + (f" (waiting: {waiting['sample_id']})" if waiting else ""))
            try:
                out = orch().review(sample["thread_id"], body.decision, body.note)
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(409, f"Could not resume thread: {exc}") from exc
            if out["status"] == "paused":  # paused again on the next review: record this decision now
                held = body.decision != "approve"
                db.save_sample(conn, sample["thread_id"], sample["campaign_id"], dict(
                    waiting, decision=body.decision, intuition_note=body.note, status="Held" if held else "Yellow", telemetry=None))
            _persist(conn, sample["thread_id"], sample["campaign_id"], out)
        finally:
            conn.close()
        return _with_trace(sample["thread_id"], out)

    def _release_context(conn, sample_id: str) -> tuple[dict, dict, dict]:
        """Sample, the targets it was planned against, and its release evaluation. 409 if it was never made."""
        sample = db.get_sample(conn, sample_id)
        if sample is None:
            raise HTTPException(404, f"Unknown sample {sample_id}")
        if not sample.get("measurements") or sample["status"] in (None, "Held"):
            raise HTTPException(409, f"{sample_id} was not made, so there is nothing to release")
        targets = db.plan_targets(conn, sample["thread_id"]) or db.get_campaign(conn, sample["campaign_id"])["targets"]
        evaluation = release.evaluate(targets, sample, db.get_action(conn, sample["thread_id"], sample_id))
        return sample, targets, evaluation

    @app.get("/api/samples/{sample_id}/release")
    def release_preview(sample_id: str) -> dict:
        """Read-only: the comparison with the customer targets, the exceptions, and any decision already made."""
        conn = db.connect()
        try:
            sample, targets, evaluation = _release_context(conn, sample_id)
            existing = db.get_release(conn, sample["thread_id"], sample_id)
        finally:
            conn.close()
        return {"sample_id": sample_id, "targets": targets, "evaluation": evaluation, "release": existing, "min_note": release.MIN_NOTE}

    @app.post("/api/samples/{sample_id}/release")
    def release_signoff(sample_id: str, body: ReleaseRequest, x_role: str = Header(default="Scientist (PI)")) -> dict:
        role = next((r for r in seed_camp014.RBAC["roles"] if r["role"] == x_role), None)
        needed = seed_camp014.RBAC["decision_permissions"][body.decision]
        if role is None or needed not in role["permissions"]:
            raise HTTPException(403, f"Role '{x_role}' may not '{body.decision}' samples")
        conn = db.connect()
        try:
            sample, targets, evaluation = _release_context(conn, sample_id)
            if db.get_release(conn, sample["thread_id"], sample_id):
                raise HTTPException(409, f"{sample_id} already has a release decision")
            verdict = release.decide(evaluation, body.decision, body.note)
            with telemetry.span(
                "release.signoff", sample_id=sample_id, decision=body.decision, allowed=verdict["ok"],
                rule=verdict["rule"] or "none", exceptions=",".join(evaluation["exceptions"]) or "none", role=x_role,
            ) as rsp:
                rows = evaluation["comparison"]["rows"]
                telemetry.record_io(
                    rsp,
                    input=f"Sample {sample_id}, decision requested: {body.decision}, role: {x_role}\n"
                    f"Scientist's note: {release.clean_note(body.note) or '(none)'}\n"
                    "Targets vs measured:\n" + "\n".join(f"- {r['key']}: {r['value']} ({'met' if r['passed'] else 'missed'}; {r['basis']})" for r in rows)
                    + f"\nExceptions: {', '.join(evaluation['exceptions']) or 'none'}",
                    output=f"{'Recorded' if verdict['ok'] else 'Refused'}: {body.decision}"
                    + (f" (rule {verdict['rule']})" if verdict["rule"] else "") + f"\n{verdict['detail']}",
                )
            if not verdict["ok"]:
                raise HTTPException(409, {"rule": verdict["rule"], "detail": verdict["detail"]})
            receipt = release.make_receipt(sample, targets, evaluation, body.decision, body.note, x_role)
            db.save_release(conn, sample["thread_id"], sample["campaign_id"], sample_id, body.decision, release.clean_note(body.note), evaluation, receipt)
        finally:
            conn.close()
        return {"sample_id": sample_id, "decision": body.decision, "receipt": receipt, "evaluation": evaluation}

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
