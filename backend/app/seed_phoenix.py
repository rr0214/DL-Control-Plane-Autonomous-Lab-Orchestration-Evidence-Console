"""Seed Arize Phoenix with six curated historical traces, human annotations, and a golden dataset.

This follows Hamel Husain's error-analysis workflow:
  1. Read real traces end to end.
  2. Open-code each one: write a short note naming the FIRST upstream failure (not the symptom).
  3. Label it Pass or Fail.
  4. Promote the labeled cases into a golden dataset that future evals run against.

IMPORTANT: these traces are curated, illustrative examples written for the demo. They are
NOT production data. They live in their own Phoenix project (`sdl-control-plane-seed`) and
every annotation carries annotator `seed-script`, so they can never be confused with live runs
in `sdl-control-plane`.

Run it with:   python -m app.seed_phoenix        (from backend/, Phoenix must be running)
Idempotent:    if the dataset `sdl-golden-eval-v1` already exists, it exits without writing.
Token-free:    no LLM calls; everything comes from the fixture below.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

SEED_PROJECT = "sdl-control-plane-seed"
DATASET_NAME = "sdl-golden-eval-v1"
ANNOTATOR = "seed-script"
CAMPAIGN_ID = "CAMP-014"
GOAL = "Improve oxidation resistance of Nb-Ti-Cr-Al refractory alloys"


@dataclass(frozen=True)
class SeedTrace:
    key: str
    title: str
    composition: str
    processing: str
    policy_status: str  # Allowed | Blocked
    policy_rule: str  # RESTRICTED_ELEMENT | DUPLICATE_CONDITION | PASS
    cv_confidence: float | None  # None when the candidate never reached the workcell
    triage_status: str | None  # Green | Yellow | Red | None
    outcome: str  # Pass | Fail (human label on the end-to-end result)
    first_failure: str  # graph node where things first went wrong, or "none"
    note: str  # one-line open-coding note
    expected_status: str  # what the golden dataset says SHOULD have happened
    expected_rule: str
    scientist_override: bool = False
    days_ago: int = 1
    tags: list[str] = field(default_factory=list)


SEED_TRACES: list[SeedTrace] = [
    SeedTrace(
        key="clean-pass-1",
        title="Clean pass: new route for a known-good composition",
        composition="Nb40-Ti30-Cr20-Al10",
        processing="Additive/Anneal",
        policy_status="Allowed",
        policy_rule="PASS",
        cv_confidence=0.95,
        triage_status="Green",
        outcome="Pass",
        first_failure="none",
        note="No upstream failure: Policy allowed a new route, SEM confidence 0.95, auto-advanced.",
        expected_status="Green",
        expected_rule="PASS",
        days_ago=12,
        tags=["clean_pass"],
    ),
    SeedTrace(
        key="clean-pass-2",
        title="Clean pass: novel composition, Arc-Melt",
        composition="Nb40-Ti25-Cr20-Al15",
        processing="Arc-Melt",
        policy_status="Allowed",
        policy_rule="PASS",
        cv_confidence=0.96,
        triage_status="Green",
        outcome="Pass",
        first_failure="none",
        note="No upstream failure: no prior run, no restricted element, clean SEM and XRD, auto-advanced.",
        expected_status="Green",
        expected_rule="PASS",
        days_ago=10,
        tags=["clean_pass"],
    ),
    SeedTrace(
        key="hf-restricted",
        title="Restricted element proposed (Hf)",
        composition="Nb40-Ti25-Hf15-Al20",
        processing="Arc-Melt",
        policy_status="Blocked",
        policy_rule="RESTRICTED_ELEMENT",
        cv_confidence=None,
        triage_status=None,
        outcome="Pass",
        first_failure="propose_candidates",
        note="First failure: planner proposed Hf (restricted). Policy Kernel blocked it before any sample was made, so the end result is correct.",
        expected_status="Blocked",
        expected_rule="RESTRICTED_ELEMENT",
        days_ago=8,
        tags=["boundary_probe", "caught_downstream"],
    ),
    SeedTrace(
        key="run-088-repeat",
        title="Repeat of failed Run-088 (Arc-Melt)",
        composition="Nb50-Ti20-Cr15-Al15",
        processing="Arc-Melt",
        policy_status="Blocked",
        policy_rule="DUPLICATE_CONDITION",
        cv_confidence=None,
        triage_status=None,
        outcome="Pass",
        first_failure="propose_candidates",
        note="First failure: planner repeated Run-088 (cracked in cooldown) without using check_negative_runs. Policy Kernel blocked the duplicate.",
        expected_status="Blocked",
        expected_rule="DUPLICATE_CONDITION",
        days_ago=6,
        tags=["boundary_probe", "caught_downstream"],
    ),
    SeedTrace(
        key="false-positive-yellow",
        title="False-positive Yellow pause on a clean novel alloy",
        composition="Nb35-Ti30-Cr20-Al15",
        processing="Additive/Anneal",
        policy_status="Allowed",
        policy_rule="PASS",
        cv_confidence=0.94,
        triage_status="Yellow",
        outcome="Fail",
        first_failure="triage_and_hitl",
        note="First failure: Yellow trigger fired on a clean 0.94 scan (threshold too tight in that build), so the scientist reviewed a sample that needed no review.",
        expected_status="Green",
        expected_rule="PASS",
        scientist_override=False,
        days_ago=4,
        tags=["false_positive", "hitl_noise"],
    ),
    SeedTrace(
        key="missed-blurry-sem",
        title="Missed blurry SEM scan auto-advanced",
        composition="Nb45-Ti25-Cr20-Al10",
        processing="Additive/Anneal",
        policy_status="Allowed",
        policy_rule="PASS",
        cv_confidence=0.86,
        triage_status="Green",
        outcome="Fail",
        first_failure="triage_and_hitl",
        note="First failure: blurry SEM scan scored 0.86 and auto-advanced as Green; the scan should have gone to a scientist as Yellow.",
        expected_status="Yellow",
        expected_rule="PASS",
        days_ago=2,
        tags=["false_negative", "sensor_ambiguity"],
    ),
]


def _hex_span_id(ctx: Any) -> str:
    return format(ctx.span_id, "016x")


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def emit_trace(provider: Any, t: SeedTrace) -> str:
    """Write one trace (root + node spans + child spans) with historical timestamps. Returns the root span id."""
    from opentelemetry import trace

    tracer = provider.get_tracer("sdl-control-plane-seed")
    start = datetime.now(timezone.utc) - timedelta(days=t.days_ago, minutes=17)
    cursor = start

    def child(parent_ctx: Any, name: str, ms: int, attrs: dict[str, Any]) -> Any:
        nonlocal cursor
        sp = tracer.start_span(name, context=parent_ctx, start_time=_ns(cursor))
        for k, v in attrs.items():
            if v is not None:
                sp.set_attribute(k, v)
        end = cursor + timedelta(milliseconds=ms)
        return sp, end

    root = tracer.start_span("campaign.plan", start_time=_ns(start))
    common = {"campaign_id": CAMPAIGN_ID, "mcp_mode": "fastmcp"}
    for k, v in {
        **common,
        "seed.illustrative": True,
        "seed.scenario": t.key,
        "seed.title": t.title,
        "input.value": f"{GOAL} | candidate {t.composition} via {t.processing}",
        "policy_status": t.policy_status,
        "scientist_override": t.scientist_override,
    }.items():
        root.set_attribute(k, v)
    root_ctx = trace.set_span_in_context(root)

    steps: list[tuple[str, int, dict[str, Any], list[tuple[str, int, dict[str, Any]]]]] = [
        ("node.retrieve_context", 42, dict(common), [("mcp.search_calphad_literature", 18, {"mcp_mode": "fastmcp"})]),
        (
            "node.propose_candidates",
            310,
            dict(common),
            [("mcp.propose_alloy_ratios", 24, {"mcp_mode": "fastmcp", "composition": t.composition, "processing": t.processing})],
        ),
        (
            "node.policy_kernel",
            9,
            dict(common),
            [
                ("mcp.check_negative_runs", 11, {"mcp_mode": "fastmcp"}),
                (
                    "policy.check",
                    1,
                    {
                        **common,
                        "policy_status": t.policy_status,
                        "policy_rule": t.policy_rule,
                        "candidate_id": t.key,
                    },
                ),
            ],
        ),
    ]
    if t.triage_status:
        steps.append(
            (
                "node.triage_and_hitl",
                60,
                dict(common),
                [
                    (
                        "sample.triage",
                        4,
                        {
                            **common,
                            "cv_confidence": t.cv_confidence,
                            "triage_status": t.triage_status,
                            "candidate_id": t.key,
                        },
                    )
                ],
            )
        )

    for name, ms, attrs, kids in steps:
        node, node_end = child(root_ctx, name, ms, attrs)
        node_ctx = trace.set_span_in_context(node)
        kid_cursor = cursor
        for kname, kms, kattrs in kids:
            ksp = tracer.start_span(kname, context=node_ctx, start_time=_ns(kid_cursor))
            for k, v in kattrs.items():
                if v is not None:
                    ksp.set_attribute(k, v)
            ksp.end(end_time=_ns(kid_cursor + timedelta(milliseconds=kms)))
            kid_cursor += timedelta(milliseconds=kms)
        node.end(end_time=_ns(node_end))
        cursor = node_end

    root.end(end_time=_ns(cursor))
    return _hex_span_id(root.get_span_context())


def dataset_examples(root_ids: dict[str, str]) -> tuple[list[dict], list[dict], list[dict]]:
    inputs, outputs, metadata = [], [], []
    for t in SEED_TRACES:
        inputs.append(
            {
                "campaign_id": CAMPAIGN_ID,
                "goal": GOAL,
                "composition": t.composition,
                "processing": t.processing,
                "cv_confidence": t.cv_confidence,
            }
        )
        outputs.append({"expected_status": t.expected_status, "expected_rule": t.expected_rule})
        metadata.append(
            {
                "scenario": t.key,
                "title": t.title,
                "observed_outcome": t.outcome,
                "first_upstream_failure": t.first_failure,
                "tags": ",".join(t.tags),
                "source_span_id": root_ids.get(t.key, ""),
                "source_project": SEED_PROJECT,
                "illustrative": True,
            }
        )
    return inputs, outputs, metadata


def seed(base_url: str) -> str:
    from phoenix.client import Client
    from phoenix.otel import register

    client = Client(base_url=base_url)
    if any(d["name"] == DATASET_NAME for d in client.datasets.list()):
        return f"Phoenix already seeded (dataset {DATASET_NAME} exists). Nothing written."

    provider = register(
        project_name=SEED_PROJECT,
        endpoint=f"{base_url}/v1/traces",
        batch=False,
        auto_instrument=False,
        set_global_tracer_provider=False,
        verbose=False,
    )
    root_ids = {t.key: emit_trace(provider, t) for t in SEED_TRACES}
    provider.force_flush()
    time.sleep(2)  # let Phoenix ingest spans before annotations reference them

    for t in SEED_TRACES:
        span_id = root_ids[t.key]
        meta = {"annotator": ANNOTATOR, "illustrative": True, "scenario": t.key}
        client.spans.add_span_annotation(
            span_id=span_id,
            annotation_name="outcome",
            annotator_kind="HUMAN",
            label=t.outcome,
            score=1.0 if t.outcome == "Pass" else 0.0,
            explanation=t.note,
            metadata=meta,
            identifier=f"{ANNOTATOR}:outcome:{t.key}",
            sync=True,
        )
        client.spans.add_span_annotation(
            span_id=span_id,
            annotation_name="first_upstream_failure",
            annotator_kind="HUMAN",
            label=t.first_failure,
            explanation=t.note,
            metadata=meta,
            identifier=f"{ANNOTATOR}:first_failure:{t.key}",
            sync=True,
        )

    inputs, outputs, metadata = dataset_examples(root_ids)
    client.datasets.create_dataset(
        name=DATASET_NAME,
        inputs=inputs,
        outputs=outputs,
        metadata=metadata,
        dataset_description=(
            "Golden dataset for the SDL Control Plane. Six curated, illustrative cases from Hamel-style "
            "error analysis. Each row pairs a candidate with the status the system SHOULD produce."
        ),
    )
    return f"Seeded {len(SEED_TRACES)} traces into '{SEED_PROJECT}' and dataset '{DATASET_NAME}'."


def main() -> int:
    base_url = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006").rstrip("/")
    try:
        print(seed(base_url))
        return 0
    except ImportError as exc:
        print(f"Skipping Phoenix seed: missing package ({exc}).")
    except Exception as exc:  # keep ./start.sh running even if seeding fails
        print(f"Skipping Phoenix seed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
