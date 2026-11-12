"""Promote scientist overrides from LIVE Phoenix traces into a "needs expert label" dataset.

This is the "once live" half of the Hamel-style workflow: when a scientist overrides the
system (Rescan or Kill on a Yellow sample), that is a signal worth a closer look. This script
finds those live `scientist.review` spans (attribute scientist_override = true) in the
`sdl-control-plane` project and adds one row per override to the Phoenix dataset
`sdl-needs-expert-label`.

What it does NOT do: it does not decide what the system SHOULD have done. Each row carries the
scientist's decision as an observed fact, and is marked `label_status = needs_expert_label`.
An expert still reads the trace and writes the expected outcome before a row belongs in the
golden dataset.

Run it (from backend/, with Phoenix running):

    python -m app.promote_overrides              # promote new overrides
    python -m app.promote_overrides --dry-run    # show what would be added, write nothing

Safe to re-run: rows already in the dataset are skipped (matched by the review span id).
Token-free: no LLM calls. Read-only against the app: it touches only Phoenix.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Any

from . import telemetry

DATASET_NAME = "sdl-needs-expert-label"
REVIEW_SPAN = "scientist.review"
PLAN_SPAN = "campaign.plan"
TRIAGE_SPAN = "sample.triage"
SPAN_LIMIT = 1000


@dataclass
class OverrideRow:
    thread_id: str
    decision: str
    candidate_id: str | None
    cv_confidence: float | None
    triage_status: str | None
    campaign_id: str | None
    review_span_id: str
    review_trace_id: str
    plan_trace_id: str | None
    reviewed_at: str
    thread_link_ambiguous: bool

    def as_example(self, project: str) -> tuple[dict, dict, dict]:
        inputs = {
            "thread_id": self.thread_id,
            "campaign_id": self.campaign_id,
            "candidate_id": self.candidate_id,
            "cv_confidence": self.cv_confidence,
            "triage_status": self.triage_status,
        }
        # The scientist's decision is an observed fact. There is deliberately no expected_status
        # here: that is the expert's call, not ours.
        outputs = {"scientist_decision": self.decision}
        metadata = {
            "label_status": "needs_expert_label",
            "source_project": project,
            "source_review_span_id": self.review_span_id,
            "source_review_trace_id": self.review_trace_id,
            "source_plan_trace_id": self.plan_trace_id or "",
            "reviewed_at": self.reviewed_at,
            "thread_link_ambiguous": self.thread_link_ambiguous,
        }
        return inputs, outputs, metadata


@dataclass
class PromotionResult:
    project: str
    dataset: str
    dry_run: bool
    review_spans: int = 0
    overrides: int = 0
    already_present: int = 0
    added: list[OverrideRow] = field(default_factory=list)
    ambiguous_threads: list[str] = field(default_factory=list)
    dataset_size_after: int | None = None
    hit_span_limit: bool = False


def _attrs(span: dict) -> dict:
    return span.get("attributes") or {}


def _is_override(span: dict) -> bool:
    return _attrs(span).get("scientist_override") in (True, "true", "True")


def select_overrides(review_spans: list[dict]) -> list[dict]:
    return sorted((s for s in review_spans if _is_override(s)), key=lambda s: s.get("start_time", ""))


def ambiguous_threads(review_spans: list[dict]) -> set[str]:
    """Threads with more than one review span. A Yellow sample is reviewed once per plan, so a
    repeat means reviews were recorded against the same thread (see the module notes in the README
    summary printed by this script)."""
    counts: dict[str, int] = {}
    for s in review_spans:
        tid = _attrs(s).get("thread_id")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
    return {t for t, n in counts.items() if n > 1}


def _yellow_triage(triage_spans: list[dict]) -> dict | None:
    """The sample that paused for review: the Yellow triage span. The node re-runs on resume, so the
    same candidate can appear twice; the first is enough."""
    seen: set[str] = set()
    yellow = []
    for s in sorted(triage_spans, key=lambda s: s.get("start_time", "")):
        a = _attrs(s)
        if a.get("triage_status") != "Yellow":
            continue
        cid = a.get("candidate_id")
        if cid in seen:
            continue
        seen.add(cid)
        yellow.append(s)
    return yellow[0] if yellow else None


def build_rows(review_spans: list[dict], plan_spans: list[dict], triage_spans: list[dict]) -> list[OverrideRow]:
    plan_by_thread = {_attrs(p).get("thread_id"): p for p in plan_spans if _attrs(p).get("thread_id")}
    triage_by_trace: dict[str, list[dict]] = {}
    for t in triage_spans:
        triage_by_trace.setdefault(t["context"]["trace_id"], []).append(t)
    ambiguous = ambiguous_threads(review_spans)

    rows: list[OverrideRow] = []
    for review in select_overrides(review_spans):
        a = _attrs(review)
        thread_id = a.get("thread_id") or ""
        plan = plan_by_thread.get(thread_id)
        plan_trace = plan["context"]["trace_id"] if plan else None
        triage = _yellow_triage(triage_by_trace.get(plan_trace, [])) if plan_trace else None
        ta = _attrs(triage) if triage else {}
        rows.append(
            OverrideRow(
                thread_id=thread_id,
                decision=str(a.get("decision", "")),
                candidate_id=ta.get("candidate_id"),
                cv_confidence=ta.get("cv_confidence"),
                triage_status=ta.get("triage_status"),
                campaign_id=_attrs(plan).get("campaign_id") if plan else None,
                review_span_id=review["context"]["span_id"],
                review_trace_id=review["context"]["trace_id"],
                plan_trace_id=plan_trace,
                reviewed_at=review.get("start_time", ""),
                thread_link_ambiguous=thread_id in ambiguous,
            )
        )
    return rows


def _existing_review_span_ids(client: Any, dataset: str) -> tuple[bool, set[str]]:
    """Returns (dataset_exists, source_review_span_ids already in it)."""
    if not any(d["name"] == dataset for d in client.datasets.list()):
        return False, set()
    ds = client.datasets.get_dataset(dataset=dataset)
    ids = {(e.get("metadata") or {}).get("source_review_span_id") for e in ds.examples}
    return True, {i for i in ids if i}


def promote(client: Any, project: str, dataset: str = DATASET_NAME, dry_run: bool = False) -> PromotionResult:
    result = PromotionResult(project=project, dataset=dataset, dry_run=dry_run)

    review_spans = client.spans.get_spans(project_identifier=project, name=REVIEW_SPAN, limit=SPAN_LIMIT)
    result.review_spans = len(review_spans)
    result.hit_span_limit = len(review_spans) >= SPAN_LIMIT
    result.ambiguous_threads = sorted(ambiguous_threads(review_spans))
    overrides = select_overrides(review_spans)
    result.overrides = len(overrides)
    if not overrides:
        return result

    plan_spans = client.spans.get_spans(project_identifier=project, name=PLAN_SPAN, limit=SPAN_LIMIT)
    wanted_threads = {_attrs(s).get("thread_id") for s in overrides}
    plan_traces = [p["context"]["trace_id"] for p in plan_spans if _attrs(p).get("thread_id") in wanted_threads]
    triage_spans = (
        client.spans.get_spans(project_identifier=project, name=TRIAGE_SPAN, trace_ids=plan_traces, limit=SPAN_LIMIT)
        if plan_traces
        else []
    )

    rows = build_rows(review_spans, plan_spans, triage_spans)
    exists, present = _existing_review_span_ids(client, dataset)
    new_rows = [r for r in rows if r.review_span_id not in present]
    result.already_present = len(rows) - len(new_rows)
    result.added = new_rows

    if dry_run or not new_rows:
        return result

    examples = [r.as_example(project) for r in new_rows]
    inputs, outputs, metadata = ([e[i] for e in examples] for i in range(3))
    if exists:
        client.datasets.add_examples_to_dataset(dataset=dataset, inputs=inputs, outputs=outputs, metadata=metadata)
    else:
        client.datasets.create_dataset(
            name=dataset,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            dataset_description=(
                "Live scientist overrides (Rescan or Kill) pulled from Phoenix traces. Each row records what "
                "the scientist did and still needs an expert to say what the system SHOULD have done."
            ),
        )
    try:
        result.dataset_size_after = len(client.datasets.get_dataset(dataset=dataset).examples)
    except Exception:  # the count is a nicety; never fail the run over it
        result.dataset_size_after = None
    return result


def format_summary(r: PromotionResult, phoenix_url: str = telemetry.PHOENIX_UI_URL) -> str:
    lines = [
        "Scientist-override promotion" + ("  (DRY RUN, nothing written)" if r.dry_run else ""),
        f"  Phoenix:                   {phoenix_url}",
        f"  Source project (live):     {r.project}",
        f"  Review spans found:        {r.review_spans}",
        f"  Overrides (not approve):   {r.overrides}",
        f"  Already in dataset:        {r.already_present}",
        f"  {'Would add' if r.dry_run else 'Added now'}:".ljust(29) + f"{len(r.added)}",
        f"  Dataset:                   {r.dataset}"
        + (f"  ({r.dataset_size_after} examples total)" if r.dataset_size_after is not None else ""),
    ]
    if r.added:
        lines.append("")
        lines.append("Rows" + (" that would be added:" if r.dry_run else " added:"))
        for row in r.added:
            cv = f"{row.cv_confidence:.2f}" if isinstance(row.cv_confidence, (int, float)) else "n/a"
            flag = "   [thread link ambiguous]" if row.thread_link_ambiguous else ""
            lines.append(
                f"  thread {row.thread_id:<16} decision={row.decision:<7} candidate={row.candidate_id or 'n/a':<5} cv={cv}{flag}"
            )
    if r.overrides == 0:
        lines.append("")
        lines.append("No scientist overrides found yet. In the console, plan a batch and choose Rescan or Kill")
        lines.append("on the Yellow sample, then run this again.")
    if r.ambiguous_threads:
        lines.append("")
        lines.append(f"Warning: {len(r.ambiguous_threads)} thread(s) have more than one review: {', '.join(r.ambiguous_threads)}.")
        lines.append("Sample ids repeat across plans, so a later review can be recorded against an earlier thread.")
        lines.append("Rows from those threads are marked thread_link_ambiguous. Use Reset Demo between runs.")
    if r.hit_span_limit:
        lines.append("")
        lines.append(f"Warning: hit the {SPAN_LIMIT}-span read limit. Older reviews may not have been scanned.")
    if r.added and not r.dry_run:
        lines.append("")
        lines.append(f"Next: open Datasets > {r.dataset} in Phoenix. Each row still needs an expert label.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote live scientist overrides into a Phoenix dataset.")
    parser.add_argument("--dry-run", action="store_true", help="show what would be added, write nothing")
    parser.add_argument("--project", default=None, help=f"live Phoenix project (default: {telemetry.LIVE_PROJECT})")
    parser.add_argument("--dataset", default=DATASET_NAME, help=f"target dataset (default: {DATASET_NAME})")
    args = parser.parse_args(argv)

    base_url = telemetry.endpoint()
    if not telemetry.phoenix_reachable(base_url):
        print(f"Cannot reach Phoenix at {base_url}. Start it with ./start.sh and try again.")
        return 1
    try:
        from phoenix.client import Client
    except ImportError as exc:
        print(f"Missing package: {exc}. Install backend/requirements.txt first.")
        return 1

    project = args.project or telemetry.live_project()
    try:
        result = promote(Client(base_url=base_url), project, args.dataset, args.dry_run)
    except Exception as exc:
        print(f"Promotion failed: {exc}")
        return 1
    print(format_summary(result, base_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
