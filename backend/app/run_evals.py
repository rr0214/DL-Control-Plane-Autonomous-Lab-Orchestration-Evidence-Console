"""Hamel-style evals in Phoenix: golden dataset v2, a code-only experiment, and a threshold comparison.

What this does (all deterministic, no LLM, no tokens):
  1. Creates the dataset `sdl-golden-eval-v2` in Phoenix (once). Rows match the CURRENT flow:
     the Policy Kernel gate, then a pre-synthesis review decision.
  2. Runs an experiment: the task executes the REAL Policy Kernel and the REAL pre-synthesis
     risk code on each row's recipe. Plain-code evaluators score each row Pass or Fail.
  3. Optionally runs it again with a different review threshold, so the two runs can be
     compared side by side in the Phoenix Experiments view.

IMPORTANT: the expected labels below are ILLUSTRATIVE stand-ins for a materials scientist's
labels. They are written by the builder, not by a domain expert. The workflow is real; the
labels are a bootstrap. Real labels come from scientist overrides via `promote_overrides`.

Run (from backend/, Phoenix must be running):
    python -m app.run_evals                       # setup if needed, then run at threshold 0.80
    python -m app.run_evals --threshold 0.95      # run again at a stricter threshold
    python -m app.run_evals --compare             # run 0.80 and 0.95 back to back
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Any

from . import policy_kernel, presynthesis
from .db import SEED_RUNS

DATASET_NAME = "sdl-golden-eval-v2"
DEFAULT_THRESHOLD = presynthesis.REVIEW_BELOW
COMPARE_THRESHOLD = 0.95
CAMPAIGN_ID = "CAMP-014"

# Failure modes (axial coding): each one is a recurring way the system can go wrong.
FAILURE_MODES = {
    "none": "Expected to work: a clean pass.",
    "unsafe_recipe_passes_gate": "A restricted-element recipe gets through the gate.",
    "repeats_known_failure": "A recipe that already failed is allowed again.",
    "risky_recipe_skips_review": "A borderline or risky recipe is not sent to a scientist.",
    "over_escalation": "A safe recipe is sent to a scientist, wasting their time.",
}

HISTORY = [
    {"run_id": r[0], "campaign_id": r[1], "composition": r[2], "processing": r[3], "outcome": r[4], "note": r[5]}
    for r in SEED_RUNS
]

# (key, composition, processing, expected_policy, expected_rule, expected_review, failure_mode, expert note)
ROWS: list[tuple[str, str, str, str, str | None, bool, str, str]] = [
    ("clean-pass-new-route", "Nb40-Ti30-Cr20-Al10", "Additive/Anneal", "Allowed", None, False, "none",
     "Known-good composition on a new route. Comfortable margin; no review needed."),
    ("clean-pass-novel", "Nb40-Ti25-Cr20-Al15", "Arc-Melt", "Allowed", None, False, "none",
     "Novel composition, no prior run, comfortable margin; no review needed."),
    ("hf-restricted", "Nb40-Ti25-Hf15-Al20", "Arc-Melt", "Blocked", "RESTRICTED_ELEMENT", False,
     "unsafe_recipe_passes_gate", "Hafnium is restricted. The gate must block it before anything is made."),
    ("run-088-repeat", "Nb50-Ti20-Cr15-Al15", "Arc-Melt", "Blocked", "DUPLICATE_CONDITION", False,
     "repeats_known_failure", "Exact repeat of Run-088, which cracked in cooldown. Must be blocked."),
    ("borderline-control", "Nb50-Ti20-Cr15-Al15", "Additive/Anneal", "Allowed", None, True,
     "risky_recipe_skips_review", "Run-088 composition on a new route. Margin is borderline; a scientist must review first."),
    ("safe-but-novel", "Nb35-Ti30-Cr20-Al15", "Additive/Anneal", "Allowed", None, False,
     "over_escalation", "Clean, low-risk recipe. Sending this to a scientist would be noise."),
    ("missed-risk", "Nb45-Ti25-Cr20-Al10", "Additive/Anneal", "Allowed", None, True,
     "risky_recipe_skips_review",
     "Expert judges this high-Nb recipe borderline on ductility. The mock risk model has no entry for it."),
]


def dataset_examples() -> tuple[list[dict], list[dict], list[dict]]:
    inputs, outputs, metadata = [], [], []
    for key, comp, proc, policy, rule, review, mode, note in ROWS:
        inputs.append({"campaign_id": CAMPAIGN_ID, "composition": comp, "processing": proc})
        outputs.append({"expected_policy": policy, "expected_rule": rule or "PASS", "expected_review": review})
        metadata.append({
            "scenario": key,
            "failure_mode": mode,
            "expert_note": note,
            "label_source": "illustrative (builder-written, not a domain expert)",
            "illustrative": True,
        })
    return inputs, outputs, metadata


# ---- the task: run the real system code ---------------------------------------------------------

def run_system(composition: str, processing: str, threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    """Gate first, then the pre-synthesis review decision. Uses the production functions."""
    verdict = policy_kernel.check({"candidate_id": "eval", "composition": composition, "processing": processing}, HISTORY)
    if not verdict.allowed:
        return {"policy": "Blocked", "rule": verdict.rule, "review_required": False, "margin": None}
    risk = presynthesis.risk_signals(composition, processing)
    review = risk["predicted_ductility_margin"] < threshold or bool(risk["restricted_elements"])
    return {
        "policy": "Allowed",
        "rule": "PASS",
        "review_required": review,
        "margin": risk["predicted_ductility_margin"],
        "blast_radius": risk["furnace_blast_radius"],
    }


# ---- evaluators: plain code, binary Pass/Fail --------------------------------------------------

def gate_correct(output: dict, expected: dict) -> dict:
    ok = output["policy"] == expected["expected_policy"] and output["rule"] == expected["expected_rule"]
    return {"score": 1.0 if ok else 0.0, "label": "Pass" if ok else "Fail",
            "explanation": f"gate said {output['policy']}/{output['rule']}, expected {expected['expected_policy']}/{expected['expected_rule']}"}


def review_correct(output: dict, expected: dict) -> dict:
    ok = output["review_required"] == expected["expected_review"]
    return {"score": 1.0 if ok else 0.0, "label": "Pass" if ok else "Fail",
            "explanation": f"review_required={output['review_required']}, expected {expected['expected_review']} (margin {output['margin']})"}


EVALUATORS = {"gate_correct": gate_correct, "review_correct": review_correct}


def score_rows(threshold: float) -> list[dict]:
    """Pure local scoring, used by tests and by the summary table."""
    rows = []
    for key, comp, proc, policy, rule, review, mode, _note in ROWS:
        out = run_system(comp, proc, threshold)
        exp = {"expected_policy": policy, "expected_rule": rule or "PASS", "expected_review": review}
        g, r = gate_correct(out, exp), review_correct(out, exp)
        rows.append({"scenario": key, "failure_mode": mode, "gate": g["label"], "review": r["label"],
                     "passed": g["score"] == 1.0 and r["score"] == 1.0})
    return rows


def summary(thresholds: tuple[float, ...] = (DEFAULT_THRESHOLD, COMPARE_THRESHOLD)) -> dict[str, Any]:
    """Read-only snapshot for the console: the same scoring the Phoenix experiment uses, computed locally."""
    runs = []
    for t in thresholds:
        rows = score_rows(t)
        runs.append({"threshold": t, "passed": sum(r["passed"] for r in rows), "total": len(rows), "rows": rows})
    return {
        "dataset": DATASET_NAME,
        "labels": "illustrative (builder-written, not a domain expert)",
        "failure_modes": {k: v for k, v in FAILURE_MODES.items() if k != "none"},
        "runs": runs,
    }


def format_summary(threshold: float) -> str:
    rows = score_rows(threshold)
    by_mode: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by_mode[r["failure_mode"]].append(r["passed"])
    lines = [f"Review threshold {threshold:.2f}: {sum(r['passed'] for r in rows)}/{len(rows)} rows pass", ""]
    for r in rows:
        lines.append(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['scenario']:<22} [{r['failure_mode']}]  gate={r['gate']} review={r['review']}")
    return "\n".join(lines)


# ---- Phoenix plumbing ---------------------------------------------------------------------------

def ensure_dataset(client: Any):
    if not any(d["name"] == DATASET_NAME for d in client.datasets.list()):
        inputs, outputs, metadata = dataset_examples()
        client.datasets.create_dataset(
            name=DATASET_NAME, inputs=inputs, outputs=outputs, metadata=metadata,
            dataset_description="Golden dataset v2 for the pre-synthesis flow. Illustrative labels; failure_mode in metadata.",
        )
    return client.datasets.get_dataset(dataset=DATASET_NAME)


def run_experiment(client: Any, dataset: Any, threshold: float) -> Any:
    def task(input):  # noqa: A002 - Phoenix binds this name
        return run_system(input["composition"], input["processing"], threshold)

    return client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators=EVALUATORS,
        experiment_name=f"gate+review @ threshold {threshold:.2f}",
        experiment_description="Plain-code evaluators over the real Policy Kernel and pre-synthesis review code.",
        experiment_metadata={"review_threshold": threshold, "llm": "none"},
        print_summary=False,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Hamel-style evals in Phoenix.")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--compare", action="store_true", help=f"also run at {COMPARE_THRESHOLD:.2f} for a side-by-side view")
    ap.add_argument("--local", action="store_true", help="score locally and print only; do not touch Phoenix")
    args = ap.parse_args(argv)
    thresholds = [args.threshold] + ([COMPARE_THRESHOLD] if args.compare else [])

    if args.local:
        for t in thresholds:
            print(format_summary(t), "\n")
        return 0

    from . import telemetry

    base_url = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006").rstrip("/")
    if not telemetry.phoenix_reachable(base_url):
        print(f"Cannot reach Phoenix at {base_url}. Start it with ./start.sh, then run this again.")
        return 1
    from phoenix.client import Client

    client = Client(base_url=base_url)
    dataset = ensure_dataset(client)
    for t in thresholds:
        run_experiment(client, dataset, t)
        print(format_summary(t), "\n")
    print(f"Open Phoenix at {base_url} > Datasets > {DATASET_NAME} > Experiments to compare the runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
