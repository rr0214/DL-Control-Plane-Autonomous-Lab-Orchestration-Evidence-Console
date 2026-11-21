"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

// Error-analysis method (Hamel Husain). The numbers in the result panel come live from the backend,
// which scores the golden dataset with the same code the Phoenix experiment uses.

type Row = { scenario: string; failure_mode: string; gate: string; review: string; passed: boolean };
type Run = { threshold: number; passed: number; total: number; rows: Row[] };
type Summary = { dataset: string; labels: string; failure_modes: Record<string, string>; runs: Run[] };

const METHOD: { step: string; today: string; next: string }[] = [
  {
    step: "1. Read traces",
    today: "Live runs and 6 seeded examples in Phoenix",
    next: "50 to 100 scenarios, including real setup agent runs",
  },
  {
    step: "2. Mark Pass/Fail and the first failure",
    today: "Done by me",
    next: "Done by a materials scientist",
  },
  {
    step: "3. Group into failure modes",
    today: "4 modes: unsafe recipe passes the gate, known failure repeated, risky recipe skips review, safe recipe over-escalated",
    next: "Re-group from real scientist notes",
  },
  {
    step: "4. Build a check per mode",
    today: "2 plain-code checks, no LLM judge",
    next: "More code checks, then a judge for the setup agent's rationale, validated against human labels",
  },
  {
    step: "5. Feed overrides back",
    today:
      "A reject and its note flow into a holding dataset, grouped by theme (for example, furnace blast radius)",
    next: "An expert labels each row, and it joins the golden set",
  },
];

const pct = (t: number) => t.toFixed(2);

type UsageRow = {
  thread_id: string;
  llm_mode: string | null;
  created_at: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
  models: string[];
};
type Usage = {
  plans: UsageRow[];
  real_plans: number;
  mock_plans: number;
  avg_cost_usd: number | null;
  avg_latency_ms: number | null;
  price_note: string;
};

export default function EvalsTab() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    apiFetch(`/api/evals/summary`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((b: Summary) => setData(b))
      .catch(() => setError(true));
    apiFetch(`/api/usage/summary`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((b: Usage | null) => setUsage(b))
      .catch(() => setUsage(null));
  }, []);

  const base = data?.runs[0];
  const strict = data?.runs[1];
  const caught =
    base && strict ? base.rows.filter((r, i) => !r.passed && strict.rows[i].passed).map((r) => r.scenario) : [];
  const flagged =
    base && strict ? base.rows.filter((r, i) => r.passed && !strict.rows[i].passed).map((r) => r.scenario) : [];

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-lg font-semibold text-slate-900">How I evaluate this system</h2>
        <p className="mt-1 text-sm text-slate-600">
          I evaluate the whole system, not just the model: read real traces, find where it fails first, group the failures,
          then build the cheapest check for each.
        </p>

        <div className="mt-4 hidden overflow-hidden rounded-lg ring-1 ring-slate-200 md:block">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Step</th>
                <th className="px-3 py-2">Today</th>
                <th className="px-3 py-2">Next</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {METHOD.map((m) => (
                <tr key={m.step} className="align-top">
                  <td className="px-3 py-3 font-semibold text-slate-900">{m.step}</td>
                  <td className="px-3 py-3 text-slate-700">{m.today}</td>
                  <td className="px-3 py-3 text-slate-700">{m.next}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ul className="mt-4 space-y-2 md:hidden">
          {METHOD.map((m) => (
            <li key={m.step} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="font-semibold text-slate-900">{m.step}</div>
              <p className="mt-1 text-slate-700">
                <span className="font-medium text-slate-900">Today: </span>
                {m.today}
              </p>
              <p className="mt-1 text-slate-700">
                <span className="font-medium text-slate-900">Next: </span>
                {m.next}
              </p>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Result: the review threshold</h2>
        {error && (
          <p className="mt-3 text-sm text-rose-700">Could not load results. Start the API with ./start.sh and refresh.</p>
        )}
        {!data && !error && <p className="mt-3 text-sm text-slate-500">Loading...</p>}
        {data && base && strict && (
          <>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {[base, strict].map((r) => (
                <div key={r.threshold} className="rounded-lg bg-slate-50 p-4 ring-1 ring-slate-200">
                  <div className="text-xs text-slate-600">
                    Review threshold {pct(r.threshold)}
                    {r === base ? " (current)" : " (stricter)"}
                  </div>
                  <div className="mt-1 text-3xl font-semibold text-slate-900">
                    {r.passed} of {r.total} <span className="text-base font-normal text-slate-600">pass</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-sm text-slate-700">
              Tightening the threshold caught {caught.length} missed {caught.length === 1 ? "risk" : "risks"} but sent{" "}
              {flagged.length} safe {flagged.length === 1 ? "recipe" : "recipes"} to a scientist, so the threshold alone is
              not the fix.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
              {caught.map((s) => (
                <span key={s} className="rounded-full bg-emerald-100 px-2 py-0.5 font-medium text-emerald-800">
                  caught: {s}
                </span>
              ))}
              {flagged.map((s) => (
                <span key={s} className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-900">
                  over-flagged: {s}
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-lg font-semibold text-slate-900">Cost and latency per plan</h2>
        <p className="mt-1 text-sm text-slate-600">
          Measured from real LLM calls only. A mock plan makes no calls and costs nothing.
        </p>
        {!usage || usage.real_plans === 0 ? (
          <p className="mt-3 text-sm text-slate-600">
            No real LLM plan yet ({usage?.mock_plans ?? 0} mock). Set an API key, then run Plan next batch in the Console tab.
          </p>
        ) : (
          <>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-slate-50 p-4 ring-1 ring-slate-200">
                <div className="text-xs text-slate-600">Average cost per plan ({usage.real_plans} real)</div>
                <div className="mt-1 text-3xl font-semibold text-slate-900">
                  {usage.avg_cost_usd === null ? "n/a" : `$${usage.avg_cost_usd.toFixed(4)}`}
                </div>
              </div>
              <div className="rounded-lg bg-slate-50 p-4 ring-1 ring-slate-200">
                <div className="text-xs text-slate-600">Average LLM time per plan</div>
                <div className="mt-1 text-3xl font-semibold text-slate-900">
                  {((usage.avg_latency_ms ?? 0) / 1000).toFixed(1)}s
                </div>
              </div>
            </div>
            <table className="mt-3 w-full text-left text-xs">
              <thead className="uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-1 pr-3">Plan</th>
                  <th className="py-1 pr-3">Calls</th>
                  <th className="py-1 pr-3">Tokens in / out</th>
                  <th className="py-1 pr-3">Cost</th>
                  <th className="py-1">LLM time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {usage.plans
                  .filter((p) => p.calls > 0)
                  .map((p) => (
                    <tr key={p.thread_id}>
                      <td className="py-1 pr-3 font-mono">{p.thread_id}</td>
                      <td className="py-1 pr-3">{p.calls}</td>
                      <td className="py-1 pr-3">
                        {p.input_tokens.toLocaleString()} / {p.output_tokens.toLocaleString()}
                      </td>
                      <td className="py-1 pr-3">{p.cost_usd === null ? "n/a" : `$${p.cost_usd.toFixed(4)}`}</td>
                      <td className="py-1">{(p.latency_ms / 1000).toFixed(1)}s</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </>
        )}
        <p className="mt-3 text-[11px] text-amber-800">{usage?.price_note ?? "Prices are set by hand. Verify against current pricing."}</p>
      </div>

      <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900 ring-1 ring-amber-200">
        Seven illustrative cases, labeled by the builder, not a domain expert. This shows the method works end to end. Real
        evidence needs real traces and expert labels.
      </div>

      <a
        href="http://localhost:6006"
        target="_blank"
        rel="noreferrer"
        className="inline-flex rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        Open in Phoenix ↗
      </a>
    </div>
  );
}
