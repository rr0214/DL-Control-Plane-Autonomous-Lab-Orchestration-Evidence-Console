"""S6 runner. Sends every case through the real loop (plan, scientist action, release attempt) with Phoenix
tracing on, one trace per case, and writes results.json and the review CSV.

Safe by default:
  - each case runs on its own throwaway database, so your real campaign history is never touched
  - spend is added up from the logged token usage; the batch stops before the next case once it reaches --max-usd
  - traces go to their own Phoenix project (sdl-s6), not the live app's project
  - cost uses the hand-set price table in llm_usage.py, which is unverified: treat the total as an estimate

From backend/ (start Phoenix first if you want trace links):
    python -m app.s6_runner                  # all 30 cases: 28 real Claude + 2 mock
    python -m app.s6_runner --mock-only      # all cases on the mock fallback: free, checks the plumbing
    python -m app.s6_runner --only S6-001,S6-002
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "s6"
DEFAULT_MAX_USD = 3.0
S6_PROJECT = "sdl-s6"
REVIEWER = {"X-Role": "Scientist (PI)"}


def trace_headers(extra: dict | None = None) -> dict:
    """Headers that carry the current trace into the API call. Without this, Phoenix's web instrumentation
    starts a new trace for each request and one case would be split into three traces."""
    from opentelemetry.propagate import inject

    from .config import access_password

    headers = dict(extra or {})
    if access_password():  # the runners call the API in process, so they need the shared password when one is set
        headers["X-Access-Password"] = access_password()
    inject(headers)
    return headers


def seed_history(conn, samples: list) -> None:
    """Write earlier decided samples into this case's database, oldest first."""
    from . import db

    for n, (composition, processing, status, decision, note) in enumerate(samples, 1):
        db.save_sample(
            conn,
            "s6-history",
            "CAMP-014",
            {
                "sample_id": f"H-{n}",
                "candidate_id": f"H-{n}",
                "composition": composition,
                "processing": processing,
                "status": status,
                "decision": decision,
                "intuition_note": note,
                "telemetry": {},
            },
        )


def phoenix_project_id(project: str, base: str) -> str | None:
    """Look up the project's id in a running Phoenix. None when Phoenix is down or the project is missing."""
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/v1/projects", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8")).get("data", [])
    except Exception:
        return None
    return next((p["id"] for p in data if p.get("name") == project), None)


def trace_url(base: str, project_id: str | None, trace_id: str) -> str:
    if not (project_id and trace_id):
        return ""
    return f"{base.rstrip('/')}/projects/{project_id}/traces/{trace_id}"


def flatten(case: dict, plan: dict | None, review: dict | None, release: dict | None, totals: dict | None, error: str | None) -> str:
    """One readable line: what the loop ended with."""
    if error:
        return f"ERROR: {error}"
    last = review or plan or {}
    parts = [f"status={last.get('status')}", f"setup_mode={(plan or {}).get('setup_mode') or 'mock'}"]
    if (plan or {}).get("setup_mode") == "mock_fallback":
        parts.append(f"setup_error={(plan or {}).get('setup_error')}")
    cands = (plan or {}).get("candidates", [])
    blocked = sorted({v["rule"] for v in (plan or {}).get("verdicts", []) if not v["allowed"]})
    parts.append(f"candidates={len(cands)} blocked={','.join(blocked) or 'none'}")
    if cands and cands[0].get("origin") == "optimizer":
        parts.append(f"pick={cands[0]['composition']} via {cands[0]['processing']}")
    pending = (plan or {}).get("pending")
    if pending:
        parts.append(f"paused for review ({pending.get('sample_id')}, {pending.get('status')})")
    if case["review"]:
        triage = (review or {}).get("triage") or []
        made = triage[0] if triage else None
        parts.append(
            f"scientist={case['review']['decision']}"
            + (f" -> made, status {made['status']}, check flags {','.join((made.get('measurement_check') or {}).get('flags', [])) or 'none'}" if made else " -> not made")
        )
    diags = [t["diagnosis"] for t in (review or {}).get("triage", []) if t.get("diagnosis")]
    if diags:
        g = diags[0]["gate"]
        parts.append(f"diagnosis={g['final_action']} ({diags[0]['mode']}; gate {'allowed' if g['allowed'] else 'overrode: ' + str(g['rule'])})")
    if case["release"]:
        if release and release.get("ok"):
            parts.append(f"release {'granted' if release['decision'] == 'release' else 'withhold recorded'}, exceptions {','.join(release.get('exceptions') or []) or 'none'}")
        elif release:
            parts.append(f"release {case['release']['decision']} refused ({release.get('rule') or release.get('detail')})")
    if totals:
        cost = totals.get("cost_usd")
        parts.append(f"llm_calls={totals['calls']} cost={'$%.4f' % cost if cost is not None else ('$0' if not totals['calls'] else 'n/a')}")
    return "; ".join(parts)


def run_case(client, case: dict, workdir: Path, tracer_span) -> dict:
    from . import db
    from .telemetry import span

    case_id = case["case_id"]
    path = workdir / f"{case_id}.db"
    path.unlink(missing_ok=True)
    os.environ["SDL_DB_PATH"] = str(path)
    conn = db.connect()
    try:
        seed_history(conn, case["history_seed"])
    finally:
        conn.close()

    saved_key = os.environ.get("ANTHROPIC_API_KEY")
    if case["mode"] == "mock":
        os.environ["ANTHROPIC_API_KEY"] = ""  # the fallback path: config reads this at call time
    started = time.perf_counter()
    plan = review = release = totals = None
    error = None
    trace_id = ""
    thread = f"s6-{case_id.lower()}"
    try:
        with span("s6.case", kind="CHAIN", case_id=case_id, case_kind=case["kind"], **{f"dim.{k}": v for k, v in case["dims"].items()}) as sp:
            ctx = sp.get_span_context()
            trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else ""
            r = client.post("/api/campaigns/plan", json={"campaign_id": "CAMP-014", "thread_id": thread, "targets": case["targets"]}, headers=trace_headers())
            if r.status_code != 200:
                raise RuntimeError(f"plan failed HTTP {r.status_code}: {r.text[:200]}")
            plan = r.json()
            totals = plan.get("llm_totals")
            sample_id = (plan.get("pending") or {}).get("sample_id")
            if case["review"] and sample_id:
                r = client.post(f"/api/samples/{sample_id}/review", json=case["review"], headers=trace_headers(REVIEWER))
                if r.status_code != 200:
                    raise RuntimeError(f"review failed HTTP {r.status_code}: {r.text[:200]}")
                review = r.json()
                totals = review.get("llm_totals") or totals
            if case["release"] and sample_id:
                r = client.post(f"/api/samples/{sample_id}/release", json=case["release"], headers=trace_headers(REVIEWER))
                body = r.json()
                if r.status_code == 200:
                    release = {"ok": True, "decision": body["decision"], "exceptions": body["evaluation"].get("exceptions", [])}
                else:
                    detail = body.get("detail")
                    release = {"ok": False, "rule": detail.get("rule") if isinstance(detail, dict) else None,
                               "detail": detail.get("detail") if isinstance(detail, dict) else str(detail)}
            sp.set_attribute("case.final_output", flatten(case, plan, review, release, totals, None)[:500])
    except Exception as exc:  # one bad case must not stop the batch
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key
    return {
        "case_id": case_id,
        "mode": case["mode"],
        "trace_id": trace_id,
        "final_output": flatten(case, plan, review, release, totals, error),
        "error": error,
        "setup_mode": (plan or {}).get("setup_mode"),
        "setup_error": (plan or {}).get("setup_error"),
        "llm_totals": totals or {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": None},
        "seconds": round(time.perf_counter() - started, 2),
    }


def summarize(results: list[dict], skipped: list[str], max_usd: float, stopped: bool) -> str:
    tot = {"calls": 0, "in": 0, "out": 0, "cw": 0, "cr": 0, "cost": 0.0}
    unpriced = 0
    for r in results:
        t = r["llm_totals"]
        tot["calls"] += t.get("calls", 0)
        tot["in"] += t.get("input_tokens", 0)
        tot["out"] += t.get("output_tokens", 0)
        tot["cw"] += t.get("cache_write_tokens", 0)
        tot["cr"] += t.get("cache_read_tokens", 0)
        if t.get("calls") and t.get("cost_usd") is None:
            unpriced += 1
        tot["cost"] += t.get("cost_usd") or 0.0
    read_pool = tot["in"] + tot["cw"] + tot["cr"]
    rate = f"{100 * tot['cr'] / read_pool:.1f}%" if read_pool else "n/a"
    lines = [
        "---- S6 batch summary ----",
        f"cases run: {len(results)}  errors: {sum(1 for r in results if r['error'])}  skipped: {len(skipped)}",
        f"LLM calls: {tot['calls']}",
        f"logged cost: ${tot['cost']:.4f} (estimate from the hand-set price table; cap ${max_usd:.2f})",
        f"tokens: {tot['in']} input, {tot['out']} output",
        f"cache hits: {tot['cr']} tokens read from cache, {tot['cw']} written; cache hit rate {rate}",
    ]
    fallbacks = [r for r in results if r.get("setup_mode") == "mock_fallback"]
    lines.append(f"setup agent fallbacks to mock: {len(fallbacks)} of {sum(1 for r in results if r.get('mode') == 'real')} real case(s)")
    if fallbacks:
        lines.append(f"WARNING: setup fell back to mock in {', '.join(r['case_id'] for r in fallbacks)}; first reason: {fallbacks[0].get('setup_error')}")
    if unpriced:
        lines.append(f"WARNING: {unpriced} case(s) used a model with no price, so their cost is not in the total")
    if stopped:
        lines.append(f"STOPPED: spend reached the ${max_usd:.2f} cap; skipped {', '.join(skipped)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    finally:
        logging.disable(logging.NOTSET)


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the S6 cases through the loop with Phoenix tracing.")
    ap.add_argument("--mock-only", action="store_true", help="run every case on the mock fallback (no API calls, no cost)")
    ap.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD, help="stop before the next case once spend reaches this (default 3.00)")
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--out", default=str(DATA_DIR), help="folder for results.json and s6_cases.csv")
    args = ap.parse_args(argv)

    os.environ.setdefault("SDL_PHOENIX_PROJECT", S6_PROJECT)
    out_dir = Path(args.out)
    work = out_dir / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    from . import config, synth_cases, telemetry
    from .telemetry import PHOENIX_UI_URL

    cases = synth_cases.load()
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c["case_id"] in wanted]
    if args.mock_only:
        cases = [dict(c, mode="mock", dims=dict(c["dims"], mode="mock")) for c in cases]
    if any(c["mode"] == "real" for c in cases) and not config.anthropic_key():
        print("ANTHROPIC_API_KEY is not set (put it in .env at the repo root). Use --mock-only to run without it.", file=sys.stderr)
        return 1

    tracing = telemetry.init_tracing()
    base = telemetry.endpoint()
    print(f"Phoenix tracing: {'ON, project ' + telemetry.live_project() + ' at ' + base if tracing else 'OFF (Phoenix not running); trace links will be blank'}")
    print(f"Running {len(cases)} case(s); mock-only={args.mock_only}; spend cap ${args.max_usd:.2f}")

    os.environ["SDL_DB_PATH"] = str(work / "boot.db")
    from fastapi.testclient import TestClient

    from .api import create_app
    from .orchestrator import CampaignOrchestrator

    client = TestClient(create_app(CampaignOrchestrator(str(work / "checkpoints.sqlite"))))
    logging.disable(logging.INFO)  # the in-process test client logs every request

    results: list[dict] = []
    skipped: list[str] = []
    spent, stopped = 0.0, False
    for case in cases:
        if stopped or spent >= args.max_usd:
            stopped = True
            skipped.append(case["case_id"])
            continue
        res = run_case(client, case, work, None)
        results.append(res)
        spent += res["llm_totals"].get("cost_usd") or 0.0
        print(f"[{len(results)}/{len(cases)}] {case['case_id']} {case['mode']:<4} {res['seconds']:>6.1f}s ${spent:.4f} total  {res['final_output'][:110]}")
        (out_dir / "results.json").write_text(json.dumps({"results": results, "skipped": skipped}, indent=2), encoding="utf-8")

    # Make sure spans reach Phoenix before looking up the project for the links.
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if tracing and hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10000)
    project_id = phoenix_project_id(telemetry.live_project(), PHOENIX_UI_URL if not tracing else base) if tracing else None
    url_base = PHOENIX_UI_URL if not tracing else base
    for r in results:
        r["trace_url"] = trace_url(url_base, project_id, r["trace_id"])
    (out_dir / "results.json").write_text(json.dumps({"results": results, "skipped": skipped, "phoenix_project": telemetry.live_project() if tracing else None}, indent=2), encoding="utf-8")

    from . import s6_export

    csv_path = s6_export.write_csv(out_dir / "results.json", out_dir / "s6_cases.csv", cases_path=synth_cases.CASES_PATH)
    print(summarize(results, skipped, args.max_usd, stopped))
    linked = sum(1 for r in results if r.get("trace_url"))
    print(f"CSV: {csv_path} ({len(results)} rows, {linked} with a Phoenix link)")
    shutil.rmtree(work, ignore_errors=True)
    return 3 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
