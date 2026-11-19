"""S6 CSV export: one row per case for the trace review.

Columns: case_id, inputs, final_output, phoenix_trace_url, notes (left empty for you to fill in).

    python -m app.s6_export
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from . import synth_cases

COLUMNS = ["case_id", "inputs", "final_output", "phoenix_trace_url", "notes"]


def describe_inputs(case: dict) -> str:
    t = case["targets"]
    hist = case["dims"]["history"].replace("_", " ")
    seeds = case["history_seed"]
    notes = [f'"{s[4]}"' for s in seeds if s[4]]
    parts = [
        f"mode: {case['mode']}",
        f"targets: {t['service_temp_c']} C, {t['min_yield_strength_mpa']} MPa, Hf at most {t['max_hafnium_at_pct']} at%",
        f"history: {hist} ({len(seeds)} earlier sample(s)" + (f"; notes: {'; '.join(notes)}" if notes else "") + ")",
    ]
    rv = case["review"]
    parts.append(f"scientist: {rv['decision']} (\"{rv['note']}\")" if rv else "scientist: no action (stays paused)")
    rl = case["release"]
    parts.append(f"release attempt: {rl['decision']} (\"{rl['note']}\")" if rl else "release attempt: none")
    return " | ".join(parts)


def write_csv(results_path: Path, csv_path: Path, cases_path: Path | None = None) -> Path:
    cases = {c["case_id"]: c for c in (json.loads(cases_path.read_text(encoding="utf-8")) if cases_path and cases_path.exists() else synth_cases.generate())}
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    csv_path = Path(csv_path)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for r in data["results"]:
            case = cases[r["case_id"]]
            if r.get("mode") == "mock" and case["mode"] != "mock":  # a --mock-only run: say so in the inputs
                case = dict(case, mode="mock")
            writer.writerow([r["case_id"], describe_inputs(case), r["final_output"], r.get("trace_url", ""), ""])
    return csv_path


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1] / "data" / "s6"
    print(write_csv(base / "results.json", base / "s6_cases.csv", synth_cases.CASES_PATH))
    sys.exit(0)
