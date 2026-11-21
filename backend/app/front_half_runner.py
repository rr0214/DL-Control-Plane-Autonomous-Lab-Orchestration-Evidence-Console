"""Front-half runner: sends the 20 front-half cases through the real loop with Phoenix tracing on.

One trace per case. Each case runs on its own throwaway database, so the live campaign history is never touched.
At every review pause (the optimizer's pick when it is risky, and the review test case) the case's scripted
scientist decision is applied, until the run completes. Spend stops the batch before the next case at --max-usd.
Traces go to their own Phoenix project (sdl-front-half).

From backend/ (start Phoenix first; the evals read the traces):
    python -m app.front_half_runner
    python -m app.front_half_runner --only FH-01,FH-06
Then score the traces:
    python -m app.front_half_evals
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from .front_half_cases import DATA_DIR
from .s6_runner import phoenix_project_id, seed_history, trace_headers, trace_url

PROJECT = "sdl-front-half"
DEFAULT_MAX_USD = 2.0
REVIEWER = {"X-Role": "Scientist (PI)"}
MAX_REVIEWS = 4


def describe(case: dict, out: dict) -> dict:
    """What the case ended with, in plain fields (also put on the case span)."""
    from .orchestrator import pick_attributes, pick_of

    final = out.get("final") or out.get("plan") or {}
    plan = out.get("plan") or {}
    pick = pick_of(plan)
    attrs = pick_attributes(final) if final else {}
    hf = [v for v in plan.get("verdicts", []) for c in plan.get("candidates", [])
          if c["candidate_id"] == v["candidate_id"] and "Hf" in c["composition"]]
    return {
        "status": final.get("status"),
        "target_check": (plan.get("target_check") or {}).get("rule") or ("possible" if plan.get("target_check") else None),
        "setup_mode": plan.get("setup_mode"),
        "pick": f"{pick['composition']} via {pick['processing']}" if pick else "none",
        "pick_gate": attrs.get("pick.gate", "none"),
        "pick_reviewed": attrs.get("pick.reviewed", False),
        "pick_decision": attrs.get("pick.decision", "none"),
        "pick_made": attrs.get("pick.made", False),
        "hafnium_candidates": [f"{v['candidate_id']} {'allowed' if v['allowed'] else 'blocked ' + str(v['rule'])}" for v in hf],
        "reviews": out.get("reviews", []),
    }


def run_case(client, case: dict, workdir: Path) -> dict:
    from . import db
    from .telemetry import record_io, set_attrs, span

    path = workdir / f"{case['case_id']}.db"
    path.unlink(missing_ok=True)
    os.environ["SDL_DB_PATH"] = str(path)
    conn = db.connect()
    try:
        seed_history(conn, case["history_seed"])
    finally:
        conn.close()

    started = time.perf_counter()
    out: dict = {"reviews": []}
    error, trace_id = None, ""
    try:
        with span("front_half.case", kind="CHAIN", case_id=case["case_id"], case_kind=case["kind"], why=case["why"]) as sp:
            ctx = sp.get_span_context()
            trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else ""
            body = {"campaign_id": "CAMP-014", "thread_id": f"fh-{case['case_id'].lower()}", "targets": case["targets"],
                    "forced_search_space": case["forced_search_space"]}
            r = client.post("/api/campaigns/plan", json=body, headers=trace_headers())
            if r.status_code != 200:
                raise RuntimeError(f"plan failed HTTP {r.status_code}: {r.text[:200]}")
            out["plan"] = out["final"] = r.json()
            for _ in range(MAX_REVIEWS):
                pending = out["final"].get("pending")
                if out["final"]["status"] != "paused" or not pending:
                    break
                r = client.post(f"/api/samples/{pending['sample_id']}/review", json=case["review"], headers=trace_headers(REVIEWER))
                if r.status_code != 200:
                    raise RuntimeError(f"review of {pending['sample_id']} failed HTTP {r.status_code}: {r.text[:200]}")
                out["reviews"].append({"sample_id": pending["sample_id"], "is_pick": bool(pending.get("is_pick")),
                                       "origin": pending.get("origin"), "decision": case["review"]["decision"]})
                out["final"] = r.json()
            d = describe(case, out)
            set_attrs(sp, {f"case.{k}": (v if isinstance(v, (str, bool, int, float)) else json.dumps(v)) for k, v in d.items()})
            record_io(sp, input=f"{case['case_id']} ({case['kind']}): {case['why']}\nTargets: {json.dumps(case['targets'])}",
                      output="\n".join(f"{k}: {v}" for k, v in d.items()))
    except Exception as exc:  # one bad case must not stop the batch
        error = f"{type(exc).__name__}: {exc}"
    totals = (out.get("final") or {}).get("llm_totals") or {"calls": 0, "cost_usd": None}
    return {
        "case_id": case["case_id"],
        "kind": case["kind"],
        "trace_id": trace_id,
        "error": error,
        "summary": describe(case, out) if out.get("plan") else None,
        "llm_totals": totals,
        "seconds": round(time.perf_counter() - started, 2),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    finally:
        logging.disable(logging.NOTSET)


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the 20 front-half cases with Phoenix tracing.")
    ap.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--out", default=str(DATA_DIR), help="folder for results.json")
    args = ap.parse_args(argv)

    os.environ.setdefault("SDL_PHOENIX_PROJECT", PROJECT)
    out_dir = Path(args.out)
    work = out_dir / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    from . import config, front_half_cases, telemetry

    cases = front_half_cases.load()
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c["case_id"] in wanted]
    if any(c["kind"] == "clean" for c in cases) and not config.anthropic_key():
        print("ANTHROPIC_API_KEY is not set; the clean cases need the real setup agent.", file=sys.stderr)
        return 1

    tracing = telemetry.init_tracing()
    base = telemetry.endpoint()
    print(f"Phoenix tracing: {'ON, project ' + telemetry.live_project() + ' at ' + base if tracing else 'OFF; the evals need traces, start Phoenix first'}")

    os.environ["SDL_DB_PATH"] = str(work / "boot.db")
    from fastapi.testclient import TestClient

    from .api import create_app
    from .orchestrator import CampaignOrchestrator

    client = TestClient(create_app(CampaignOrchestrator(str(work / "checkpoints.sqlite"))))
    logging.disable(logging.INFO)

    results, skipped, spent = [], [], 0.0
    for case in cases:
        if spent >= args.max_usd:
            skipped.append(case["case_id"])
            continue
        res = run_case(client, case, work)
        results.append(res)
        spent += res["llm_totals"].get("cost_usd") or 0.0
        s = res["summary"] or {}
        print(f"[{len(results):>2}/{len(cases)}] {case['case_id']} {case['kind']:<14} {res['seconds']:>5.1f}s ${spent:.4f}  "
              + (f"ERROR {res['error']}" if res["error"] else
                 f"status={s.get('status')} check={s.get('target_check')} pick={s.get('pick')} gate={s.get('pick_gate')} "
                 f"reviewed={s.get('pick_reviewed')} decision={s.get('pick_decision')} made={s.get('pick_made')}"))

    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if tracing and hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10000)
    project_id = phoenix_project_id(telemetry.live_project(), base) if tracing else None
    for r in results:
        r["trace_url"] = trace_url(telemetry.public_url(), project_id, r["trace_id"])  # opened in a browser
    (out_dir / "results.json").write_text(json.dumps(
        {"phoenix_project": telemetry.live_project() if tracing else None, "results": results, "skipped": skipped}, indent=2), encoding="utf-8")
    calls = sum(r["llm_totals"].get("calls", 0) for r in results)
    print(f"---- {len(results)} case(s), errors {sum(1 for r in results if r['error'])}, skipped {len(skipped)}, "
          f"LLM calls {calls}, logged cost ${spent:.4f} (estimate) ----")
    print(f"results: {out_dir / 'results.json'}")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
