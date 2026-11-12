"use client";

import { useState } from "react";
import { API, CampaignView, PlanResult, SampleRecord, Span, TriageRecord, Verdict } from "@/lib/api";

const ROLES = ["Scientist (PI)", "Operator"];

const ORIGIN_LABEL: Record<string, string> = {
  llm: "Model proposal",
  boundary_probe: "Boundary probe (policy check)",
  yellow_control: "Demo Yellow control (sensor ambiguity)",
};

function Pill({ tone, children }: { tone: "green" | "yellow" | "red" | "slate" | "blue"; children: React.ReactNode }) {
  const tones = {
    green: "bg-emerald-100 text-emerald-800 ring-emerald-300",
    yellow: "bg-amber-100 text-amber-900 ring-amber-300",
    red: "bg-rose-100 text-rose-800 ring-rose-300",
    slate: "bg-slate-200 text-slate-700 ring-slate-300",
    blue: "bg-sky-100 text-sky-800 ring-sky-300",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${tones[tone]}`}>
      {children}
    </span>
  );
}

function statusTone(status: string): "green" | "yellow" | "red" | "slate" {
  if (status === "Green") return "green";
  if (status === "Yellow") return "yellow";
  if (status === "Red") return "red";
  return "slate";
}

function depthOf(span: Span, byId: Map<string, Span>): number {
  let depth = 0;
  let parent = span.parent_span_id;
  while (parent && byId.has(parent)) {
    depth += 1;
    parent = byId.get(parent)?.parent_span_id ?? null;
  }
  return depth;
}

export default function ConsoleTab({ campaign, onChange }: { campaign: CampaignView | null; onChange: () => void }) {
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [role, setRole] = useState(ROLES[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSample, setSelectedSample] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null);

  async function runPlan() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/campaigns/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: "CAMP-014" }),
      });
      if (!res.ok) throw new Error(await res.text());
      setPlan(await res.json());
      setSelectedSample(null);
      setSelectedSpan(null);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function review(sampleId: string, decision: "approve" | "rescan" | "kill") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/samples/${sampleId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Role": role },
        body: JSON.stringify({ decision, note }),
      });
      if (!res.ok) throw new Error(`${res.status}: ${(await res.text()).slice(0, 200)}`);
      setPlan(await res.json());
      setNote("");
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const verdictById = new Map<string, Verdict>((plan?.verdicts ?? []).map((v) => [v.candidate_id, v] as const));
  const triageRows: TriageRecord[] = plan?.triage ?? [];
  const pending = plan?.pending ?? null;

  const allSamples: SampleRecord[] = [...(campaign?.seed_samples ?? []), ...(campaign?.live_samples ?? [])];
  const sample = allSamples.find((s) => s.sample_id === selectedSample) ?? null;

  const spans = plan?.trace?.spans ?? campaign?.seed_trace?.spans ?? [];
  const spanById = new Map<string, Span>(spans.map((s) => [s.span_id, s] as const));
  const traceLabel = plan ? `Trace for ${plan.thread_id}` : "Seed trace (CAMP-014)";

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      {/* Left: goal and pre-flight gate */}
      <section className="space-y-4 lg:col-span-3">
        <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Goal</h2>
            <Pill tone="blue">{campaign?.campaign.campaign_id ?? "CAMP-014"}</Pill>
          </div>
          <p className="mt-2 text-sm text-slate-800">
            {campaign?.campaign.goal ?? "Loading campaign from the backend..."}
          </p>
          <div className="mt-3 flex gap-2">
            <Pill tone="slate">Tenant {campaign?.campaign.tenant ?? "-"}</Pill>
            <Pill tone="red">{campaign?.campaign.export_control ?? "ITAR"}</Pill>
          </div>
        </div>

        <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Related literature</h2>
          <ul className="mt-2 space-y-2">
            {(plan?.literature ?? campaign?.literature ?? []).map((lit) => (
              <li key={lit.id} className="text-xs">
                <a href={lit.doi_url} target="_blank" rel="noreferrer" className="font-medium text-sky-700 hover:underline">
                  {lit.title}
                </a>
                <div className="text-slate-500">
                  {lit.authors} · {lit.year} · {lit.venue}
                </div>
                <div className="font-mono text-[11px] text-slate-400">doi:{lit.doi}</div>
              </li>
            ))}
            {!(campaign?.literature?.length || plan?.literature?.length) && (
              <li className="text-xs text-slate-500">Loading references...</li>
            )}
          </ul>
        </div>

        <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Pre-flight gate</h2>
          <p className="mt-1 text-xs text-slate-500">
            Deterministic rules run before any sample is made. No model can override them.
          </p>
          <button
            onClick={runPlan}
            disabled={busy}
            className="mt-3 w-full rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? "Working..." : "Plan next batch"}
          </button>
          {plan && (
            <p className="mt-2 text-xs text-slate-500">
              Mode: <span className="font-medium text-slate-700">{plan.llm_mode}</span>
            </p>
          )}
          <ul className="mt-3 space-y-2">
            {(plan?.candidates ?? []).map((c) => {
              const v = verdictById.get(c.candidate_id);
              return (
                <li key={c.candidate_id} className="rounded-lg border border-slate-200 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-slate-600">{c.candidate_id}</span>
                    {v ? (
                      <Pill tone={v.allowed ? "green" : "red"}>{v.allowed ? "Allowed" : "Blocked"}</Pill>
                    ) : (
                      <Pill tone="slate">Unchecked</Pill>
                    )}
                  </div>
                  <div className="mt-1 font-mono text-xs text-slate-800">{c.composition}</div>
                  <div className="text-xs text-slate-500">{c.processing}</div>
                  {v && (
                    <div className="mt-1 text-xs">
                      <span className="font-medium text-slate-700">{v.rule ?? "PASS"}</span>
                      <span className="text-slate-500"> · {v.reason}</span>
                    </div>
                  )}
                  {c.origin && (
                    <div className="mt-1 text-[11px] uppercase tracking-wide text-slate-400">
                      {ORIGIN_LABEL[c.origin] ?? c.origin}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {plan?.tool_calls?.length ? (
            <div className="mt-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Tool calls this run</h3>
              <ul className="mt-1 space-y-1 font-mono text-[11px] text-slate-600">
                {plan.tool_calls.map((tc, i) => (
                  <li key={`${tc.tool}-${i}`} className="flex items-center justify-between gap-2">
                    <span>{tc.tool}</span>
                    <Pill tone={tc.transport === "fastmcp" ? "blue" : "slate"}>
                      {tc.transport === "fastmcp" ? "FastMCP" : "direct"}
                    </Pill>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {plan?.notes?.length ? (
            <ul className="mt-3 list-disc pl-4 text-xs text-slate-500">
              {plan.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      {/* Center: live triage queue with the interactive HITL card */}
      <section className="space-y-4 lg:col-span-5">
        {error && <div className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800 ring-1 ring-rose-200">{error}</div>}

        {pending && (
          <div className="rounded-xl bg-amber-50 p-4 shadow-sm ring-1 ring-amber-300">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-amber-900">Needs a scientist: {pending.sample_id}</h2>
              <Pill tone="yellow">Yellow</Pill>
            </div>
            <p className="mt-2 text-sm text-amber-900">{pending.reason}</p>
            <div className="mt-2 font-mono text-xs text-amber-900">
              {pending.composition} · {pending.processing}
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-amber-900">
              <div>SEM CV {pending.telemetry.sem_cv_confidence.toFixed(2)}</div>
              <div>XRD match {pending.telemetry.xrd_phase_match.toFixed(2)}</div>
              <div>Crack {pending.telemetry.crack_detected ? "yes" : "no"}</div>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <label className="text-xs text-amber-900" htmlFor="role">
                Acting as
              </label>
              <select
                id="role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="rounded-md border border-amber-300 bg-white px-2 py-1 text-xs"
              >
                {ROLES.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </div>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={280}
              placeholder="One-line intuition note (optional)"
              className="mt-2 w-full rounded-md border border-amber-300 bg-white p-2 text-sm"
              rows={2}
            />
            <div className="mt-2 flex gap-2">
              <button
                disabled={busy}
                onClick={() => review(pending.sample_id, "approve")}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={busy}
                onClick={() => review(pending.sample_id, "rescan")}
                className="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Rescan
              </button>
              <button
                disabled={busy}
                onClick={() => review(pending.sample_id, "kill")}
                className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Kill
              </button>
            </div>
          </div>
        )}

        <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Live triage queue</h2>
          {triageRows.length === 0 && !pending && (
            <p className="mt-2 text-sm text-slate-500">
              No samples in triage yet. Plan a batch to start the run.
            </p>
          )}
          <ul className="mt-3 divide-y divide-slate-100">
            {triageRows.map((t) => (
              <li key={t.sample_id}>
                <button
                  onClick={() => setSelectedSample(t.sample_id)}
                  className={`flex w-full items-center justify-between gap-3 py-2 text-left hover:bg-slate-50 ${
                    selectedSample === t.sample_id ? "bg-slate-50" : ""
                  }`}
                >
                  <div>
                    <div className="font-mono text-xs text-slate-700">{t.sample_id}</div>
                    <div className="font-mono text-sm text-slate-900">{t.composition}</div>
                    <div className="text-xs text-slate-500">{t.processing}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Pill tone={statusTone(t.status)}>{t.status}</Pill>
                    <span className="text-xs text-slate-500">{t.decision ?? "pending"}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Right: evidence drawer and span inspector */}
      <section className="space-y-4 lg:col-span-4">
        <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Evidence and lineage</h2>
          {sample ? (
            <div className="mt-2 space-y-2 text-xs">
              <div className="font-mono text-slate-800">{sample.sample_id}</div>
              <div>
                Decision: <span className="font-medium">{sample.decision ?? "pending"}</span>
              </div>
              {sample.intuition_note && <div className="italic text-slate-600">&ldquo;{sample.intuition_note}&rdquo;</div>}
              <div className="rounded-md bg-slate-50 p-2 font-mono">
                <div>{sample.receipt.receipt_id}</div>
                <div className="break-all text-[11px] text-slate-500">sha256 {sample.receipt.content_sha256}</div>
                <div className="text-[11px] text-slate-500">
                  {sample.receipt.instrument} · {sample.receipt.recorded_at} · {sample.receipt.signed_by}
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-500">Select a sample in the triage queue to see its receipt.</p>
          )}
        </div>

        <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Span inspector</h2>
            <Pill tone="slate">OpenTelemetry (simulated)</Pill>
          </div>
          <p className="mt-1 text-xs text-slate-500">{traceLabel}</p>
          <ul className="mt-2 max-h-72 space-y-0.5 overflow-auto font-mono text-xs">
            {spans.map((s) => (
              <li key={s.span_id}>
                <button
                  onClick={() => setSelectedSpan(s)}
                  style={{ paddingLeft: `${depthOf(s, spanById) * 12}px` }}
                  className={`block w-full rounded px-1 py-0.5 text-left hover:bg-slate-100 ${
                    selectedSpan?.span_id === s.span_id ? "bg-slate-100" : ""
                  }`}
                >
                  {s.name} <span className="text-slate-400">{s.duration_ms.toFixed(1)}ms</span>
                </button>
              </li>
            ))}
          </ul>
          {selectedSpan && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-slate-900 p-2 text-[11px] text-slate-100">
              {JSON.stringify(selectedSpan.attributes, null, 2)}
            </pre>
          )}
        </div>
      </section>
    </div>
  );
}
