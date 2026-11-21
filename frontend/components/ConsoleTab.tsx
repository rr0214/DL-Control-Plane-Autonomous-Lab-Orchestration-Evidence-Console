"use client";

import { useState } from "react";
import LoopStrip from "./LoopStrip";
import ReleaseCard from "./ReleaseCard";
import { usePhoenixUrl, CampaignView, PlanResult, SampleRecord, Span, Targets, TriageRecord, Verdict, apiFetch } from "@/lib/api";

const ROLES = ["Scientist (PI)", "Operator"];

const ORIGIN_LABEL: Record<string, string> = {
  llm: "Model proposal",
  optimizer: "Optimizer pick (inside the setup agent's search space)",
  boundary_probe: "Policy test case (checks the safety gate)",
  yellow_control: "Review test case (forces a scientist review)",
  mock_control: "Review test case (forces a scientist review)",
};

function Pill({ tone, children }: { tone: "green" | "yellow" | "red" | "slate" | "blue"; children: React.ReactNode }) {
  const tones = {
    green: "bg-ok-100 text-ok-800 ring-ok-300",
    yellow: "bg-warn-100 text-warn-900 ring-warn-300",
    red: "bg-danger-100 text-danger-800 ring-danger-300",
    slate: "bg-ink-200 text-ink-700 ring-ink-300",
    blue: "bg-info-100 text-info-800 ring-info-300",
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

// Display only: "C-1" is shown as "Candidate 1". The underlying candidate_id is never changed.
// Revise is hidden for now: it currently behaves like Reject (the recipe is held, nothing is re-queued).
// Flip to true once Revise sends the recipe back to the setup agent. The backend still accepts "revise".
const SHOW_REVISE = false;

const candidateLabel = (id: string) => id.replace(/^C-(\d+)$/, "Candidate $1");

const TYPE_TONE: Record<string, string> = {
  LLM: "bg-ai-100 text-ai-800",
  ML: "bg-warn-100 text-warn-900",
  code: "bg-ink-200 text-ink-800",
  person: "bg-ok-100 text-ok-800",
};

// Says what kind of step this is: a language model, a numeric model, plain code, or a person.
function TypeChip({ type, mock = false }: { type: string; mock?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${TYPE_TONE[type] ?? TYPE_TONE.code}`}>
      {type}
      {mock && <span className="rounded bg-surface/70 px-1 text-[10px] uppercase">mock</span>}
    </span>
  );
}

function ColumnHeader({ title, emphasis = false }: { title: string; emphasis?: boolean }) {
  return (
    <h2 className={`flex h-8 items-center font-semibold tracking-tight text-ink-900 ${emphasis ? "text-lg" : "text-base"}`}>{title}</h2>
  );
}

// Native <details>: closed by default, keyboard accessible, no extra state to manage.
function Collapsible({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <details className="group rounded-xl bg-surface shadow-sm ring-1 ring-ink-200">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 p-4 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-ink-500">
          <span aria-hidden className="text-ink-400 transition-transform group-open:rotate-90">
            ▸
          </span>
          {title}
        </span>
        {badge}
      </summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
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
  const phoenixUrl = usePhoenixUrl();
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [role, setRole] = useState(ROLES[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSample, setSelectedSample] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null);
  const [releasePick, setReleasePick] = useState<string | null>(null);
  const [targets, setTargets] = useState<Targets | null>(null);
  const activeTargets = targets ?? campaign?.campaign.targets ?? null;
  const setTarget = (key: keyof Targets, value: string) =>
    setTargets({ ...(activeTargets as Targets), [key]: Number(value) });

  async function runPlan() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/campaigns/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: "CAMP-014", ...(activeTargets ? { targets: activeTargets } : {}) }),
      });
      if (!res.ok) {
        const text = await res.text();
        let detail = text;
        try {
          const d = JSON.parse(text).detail;
          if (typeof d === "string") detail = d; // e.g. the daily run limit message
        } catch {}
        throw new Error(detail);
      }
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

  async function review(sampleId: string, decision: "approve" | "revise" | "reject") {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/samples/${sampleId}/review`, {
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

  // Samples that were made and measured, newest first. A release decision takes a sample off the "ready" list.
  const releasedBy = new Map<string, string>((campaign?.releases ?? []).map((r) => [r.sample_id, r.decision] as const));
  const madeSamples = (campaign?.live_samples ?? []).filter((s) => s.measurements).slice(0, 5);
  const readySamples = madeSamples.filter((s) => !releasedBy.has(s.sample_id));
  const releaseId =
    (releasePick && madeSamples.some((s) => s.sample_id === releasePick) ? releasePick : null) ??
    readySamples[0]?.sample_id ??
    madeSamples[0]?.sample_id ??
    null;

  // Where the current batch is on the loop strip (index into LOOP_STAGES).
  const loopStage = !plan ? (busy ? 1 : 0) : pending ? 4 : readySamples.length > 0 ? 9 : 8;

  const spans = plan?.trace?.spans ?? campaign?.seed_trace?.spans ?? [];
  const spanById = new Map<string, Span>(spans.map((s) => [s.span_id, s] as const));
  const literature = plan?.literature ?? campaign?.literature ?? [];
  const traceLabel = plan ? `Trace for ${plan.thread_id}` : "Seed trace (CAMP-014)";

  return (
    <div>
    <LoopStrip current={loopStage} />
    <div className="grid gap-4 lg:grid-cols-12">
      {/* Left: plan the batch (goal, targets, the Plan button) and the safety gate */}
      <section className="space-y-4 lg:col-span-3">
        <ColumnHeader title="Plan the batch" />
        <div className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Goal</h2>
            <Pill tone="blue">{campaign?.campaign.campaign_id ?? "CAMP-014"}</Pill>
          </div>
          <p className="mt-2 text-sm text-ink-800">
            {campaign?.campaign.goal ?? "Loading campaign from the backend..."}
          </p>
          <div className="mt-3 flex gap-2">
            <Pill tone="slate">Tenant {campaign?.campaign.tenant ?? "-"}</Pill>
            <Pill tone="red">{campaign?.campaign.export_control ?? "ITAR"}</Pill>
          </div>
        </div>

        <div className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Customer targets</h2>
            <TypeChip type="person" />
          </div>
          <p className="mt-1 text-xs text-ink-500">Set by the customer. Default values are illustrative examples, not real customer data.</p>
          {activeTargets && (
            <div className="mt-2 space-y-2 text-xs text-ink-700">
              {([
                ["service_temp_c", "High temperature performance (min service temp, °C)"],
                ["min_yield_strength_mpa", "Strength (min yield, MPa)"],
                ["max_hafnium_at_pct", "Reduced hafnium (max Hf, at%)"],
              ] as [keyof Targets, string][]).map(([key, label]) => (
                <label key={key} className="block">
                  {label}
                  <input
                    type="number"
                    step={key === "max_hafnium_at_pct" ? 0.1 : 1}
                    value={activeTargets[key]}
                    onChange={(e) => setTarget(key, e.target.value)}
                    className="mt-0.5 w-full rounded border border-ink-300 px-2 py-1 text-sm"
                  />
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
          <button
            onClick={runPlan}
            disabled={busy}
            className="w-full rounded-lg bg-ink-900 px-3 py-2 text-sm font-medium text-surface hover:bg-ink-700 disabled:opacity-50"
          >
            {busy ? "Working..." : "Plan next batch"}
          </button>
          {plan && (
            <p className="mt-2 text-xs text-ink-500">
              Mode: <span className="font-medium text-ink-700">{plan.llm_mode}</span>
            </p>
          )}
          {plan?.llm_totals && plan.llm_totals.calls > 0 && (
            <p className="mt-1 text-xs text-ink-500">
              {plan.llm_totals.calls} LLM calls · {(plan.llm_totals.input_tokens + plan.llm_totals.output_tokens).toLocaleString()} tokens ·{" "}
              {plan.llm_totals.cost_usd === null ? "cost n/a" : `$${plan.llm_totals.cost_usd.toFixed(4)}`} ·{" "}
              {(plan.llm_totals.latency_ms / 1000).toFixed(1)}s
            </p>
          )}
        </div>

        <Collapsible title="Related literature" badge={literature.length ? <Pill tone="slate">{literature.length}</Pill> : undefined}>
          <ul className="space-y-2">
            {literature.map((lit) => (
              <li key={lit.id} className="text-xs">
                <a href={lit.doi_url} target="_blank" rel="noreferrer" className="font-medium text-info-700 hover:underline">
                  {lit.title}
                </a>
                <div className="text-ink-500">
                  {lit.authors} · {lit.year} · {lit.venue}
                </div>
                <div className="font-mono text-[11px] text-ink-400">doi:{lit.doi}</div>
              </li>
            ))}
            {literature.length === 0 && <li className="text-xs text-ink-500">Loading references...</li>}
          </ul>
          {plan && (
            <div className="mt-3 border-t border-ink-200 pt-2 text-xs text-ink-700">
              <div className="mb-1 flex items-center gap-2 font-semibold text-ink-800">
                Setup agent: directions and search space <TypeChip type="LLM" mock={plan.literature_mode === "mock"} />
              </div>
              {plan.search_space && (
                <p className="mb-1 text-ink-600">
                  Search space:{" "}
                  {plan.search_space.elements.map((e) => `${e.symbol} ${e.min_pct}-${e.max_pct}%`).join(", ")}; routes{" "}
                  {plan.search_space.routes.join(", ")}
                </p>
              )}
              {(plan.directions ?? []).length > 0 ? (
                <ul className="list-disc space-y-1 pl-4">
                  {(plan.directions ?? []).map((d) => (
                    <li key={d.direction}>
                      {d.direction} <span className="text-ink-400">[{d.cited_ids.join(", ")}]</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-ink-500">None. Without an API key this step is a plain lookup with no search space.</p>
              )}
            </div>
          )}
        </Collapsible>

        <div className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Safety gate</h2>
          <p className="mt-1 text-xs text-ink-500">
            The policy gate checks every recipe before any sample is made. No model can override it.
          </p>
          <ul className="mt-3 space-y-2">
            {(plan?.candidates ?? []).map((c) => {
              const v = verdictById.get(c.candidate_id);
              return (
                <li key={c.candidate_id} className="rounded-lg border border-ink-200 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-ink-600">{candidateLabel(c.candidate_id)}</span>
                    {v ? (
                      v.allowed && triageRows.some((t) => t.candidate_id === c.candidate_id && t.status === "Held") ? (
                        <Pill tone="red">Held</Pill>
                      ) : v.allowed && (pending?.candidate_id === c.candidate_id || triageRows.some((t) => t.candidate_id === c.candidate_id && t.status === "Yellow")) ? (
                        <Pill tone="yellow">Needs Review</Pill>
                      ) : (
                        <Pill tone={v.allowed ? "green" : "red"}>{v.allowed ? "Allowed" : "Blocked"}</Pill>
                      )
                    ) : (
                      <Pill tone="slate">Unchecked</Pill>
                    )}
                  </div>
                  <div className="mt-1 font-mono text-xs text-ink-800">{c.composition}</div>
                  <div className="text-xs text-ink-500">{c.processing}</div>
                  {v && (
                    <div className="mt-1 text-xs">
                      <span className="font-medium text-ink-700">{v.rule ?? "PASS"}</span>
                      <span className="text-ink-500"> · {v.reason}</span>
                    </div>
                  )}
                  {c.origin && (
                    <div className="mt-1 text-[11px] uppercase tracking-wide text-ink-400">
                      {ORIGIN_LABEL[c.origin] ?? c.origin}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {plan?.notes?.length ? (
            <ul className="mt-3 list-disc pl-4 text-xs text-ink-500">
              {plan.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </div>

        {plan?.tool_calls?.length ? (
          <Collapsible title="Technical details" badge={<Pill tone="slate">{plan.tool_calls.length}</Pill>}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">Tool calls this run</h3>
            <ul className="mt-1 space-y-1 font-mono text-[11px] text-ink-600">
              {plan.tool_calls.map((tc, i) => (
                <li key={`${tc.tool}-${i}`} className="flex items-center justify-between gap-2">
                  <span>{tc.tool}</span>
                  <Pill tone={tc.transport === "fastmcp" ? "blue" : "slate"}>{tc.transport === "fastmcp" ? "FastMCP" : "direct"}</Pill>
                </li>
              ))}
            </ul>
          </Collapsible>
        ) : null}
      </section>

      {/* Center: before making. The live triage queue with the interactive review card. Widest column. */}
      <section className="space-y-4 lg:col-span-6">
        <ColumnHeader title="Before making" emphasis />
        <p className="-mt-2 text-sm text-ink-500">
          The safety triage queue. A scientist reviews risky recipes here, before any sample is made.
        </p>
        {error && <div className="rounded-lg bg-danger-50 p-3 text-sm text-danger-800 ring-1 ring-danger-200">{error}</div>}

        {plan?.status === "stopped" && (
          <div className="rounded-xl bg-danger-50 p-4 shadow-sm ring-1 ring-danger-300">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-danger-900">Run stopped: impossible targets</h2>
              <Pill tone="red">{plan.target_check?.rules?.join(", ") || "Stopped"}</Pill>
            </div>
            <p className="mt-2 text-sm text-danger-900">{plan.target_check?.reason}</p>
            <p className="mt-1 text-xs text-danger-800">Nothing was picked or made. Change the targets and plan again.</p>
          </div>
        )}

        {pending && (
          <div className="rounded-xl bg-warn-50 p-4 shadow-sm ring-1 ring-warn-300">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-warn-900">Needs a scientist: {candidateLabel(pending.candidate_id)} (Pre-Synthesis Review)</h2>
              <Pill tone={pending.is_pick ? "blue" : "yellow"}>
                {pending.is_pick ? "Optimizer pick" : pending.origin === "yellow_control" ? "Review test case" : "Yellow"}
              </Pill>
            </div>
            <p className="mt-2 text-sm text-warn-900">{pending.reason}</p>
            <div className="mt-2 font-mono text-xs text-warn-900">
              {pending.composition} · {pending.processing}
            </div>
            <div className="mt-3 rounded-lg bg-surface/70 p-3 text-sm text-warn-950 ring-1 ring-warn-200">
              <div className="mb-1 flex items-center justify-between gap-2 text-[11px] font-medium uppercase tracking-wide text-warn-800">
                <span>Pre-synthesis risk signals</span>
                <Pill tone="slate">Mock model (demo values)</Pill>
              </div>
              <ul className="space-y-1">
                <li>
                  Predicted ductility (elongation):{" "}
                  <strong>
                    {pending.risk.predicted_elongation_pct.toFixed(1)}% ({pending.risk.ductility_label})
                  </strong>
                  <div className="text-xs text-warn-800">
                    Baseline {pending.risk.baseline_run}: {pending.risk.baseline_elongation_pct.toFixed(1)}% · minimum to skip
                    review: {pending.risk.min_elongation_pct.toFixed(1)}% (set by the application spec)
                  </div>
                </li>
                <li>
                  Furnace blast radius: <strong>{pending.risk.furnace_blast_radius}</strong>
                </li>
                <li>
                  Phase stability: predicted to stay single phase ({Math.round(pending.risk.phase_stability * 100)}% confidence) |
                  Restricted elements:{" "}
                  {pending.risk.restricted_elements.length ? pending.risk.restricted_elements.join(", ") : "None"}
                </li>
              </ul>
            </div>
            <p className="mt-2 text-xs text-warn-900">
              Nothing has been made yet. Approve sends this recipe to synthesis. Revise or Reject holds it.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <label className="text-xs text-warn-900" htmlFor="role">
                Acting as
              </label>
              <select
                id="role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="rounded-md border border-warn-300 bg-surface px-2 py-1 text-xs"
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
              placeholder="One-line scientist note (optional)"
              className="mt-2 w-full rounded-md border border-warn-300 bg-surface p-2 text-sm"
              rows={2}
            />
            <div className="mt-2 flex gap-2">
              <button
                disabled={busy}
                onClick={() => review(pending.sample_id, "approve")}
                className="rounded-md bg-ok-600 px-3 py-1.5 text-sm font-medium text-surface disabled:opacity-50"
              >
                Approve
              </button>
              {SHOW_REVISE && (
                <button
                  disabled={busy}
                  onClick={() => review(pending.sample_id, "revise")}
                  className="rounded-md bg-warn-600 px-3 py-1.5 text-sm font-medium text-surface disabled:opacity-50"
                >
                  Revise
                </button>
              )}
              <button
                disabled={busy}
                onClick={() => review(pending.sample_id, "reject")}
                className="rounded-md bg-danger-600 px-3 py-1.5 text-sm font-medium text-surface disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </div>
        )}

        <div className="rounded-xl bg-surface p-6 shadow-md ring-2 ring-ink-900/10">
          <h2 className="text-base font-semibold uppercase tracking-wide text-ink-700">Live triage queue</h2>
          {triageRows.length === 0 && !pending && (
            <p className="mt-3 text-base text-ink-500">
              No samples in triage yet. Plan a batch to start the run.
            </p>
          )}
          <ul className="mt-3 divide-y divide-ink-100">
            {triageRows.map((t) => (
              <li key={t.sample_id}>
                <button
                  onClick={() => setSelectedSample(t.sample_id)}
                  className={`flex w-full items-center justify-between gap-3 px-1 py-3 text-left hover:bg-ink-50 ${
                    selectedSample === t.sample_id ? "bg-ink-50" : ""
                  }`}
                >
                  <div>
                    <div className="font-mono text-xs text-ink-700">{t.sample_id}</div>
                    <div className="font-mono text-base text-ink-900">{t.composition}</div>
                    <div className="text-sm text-ink-500">{t.processing}</div>
                    {t.follow_up && <div className="mt-1 max-w-md text-xs text-ink-500">{t.follow_up}</div>}
                    {t.diagnosis && (
                      <div className="mt-1 max-w-md rounded bg-ink-50 p-1.5 text-xs text-ink-700 ring-1 ring-ink-200">
                        <TypeChip type="LLM" mock={t.diagnosis.mode === "mock"} /> Diagnosis proposed{" "}
                        <span className="font-medium">{t.diagnosis.gate.proposal.action ?? "nothing valid"}</span>
                        {t.diagnosis.gate.proposal.cause && <> (likely {t.diagnosis.gate.proposal.cause})</>}
                        {t.diagnosis.gate.proposal.reason && <div className="text-ink-500">{t.diagnosis.gate.proposal.reason}</div>}
                        <div className="mt-0.5">
                          <TypeChip type="code" /> Gate:{" "}
                          {t.diagnosis.gate.allowed ? (
                            <span className="font-medium text-ok-700">allowed, {t.diagnosis.gate.final_action}</span>
                          ) : (
                            <span className="font-medium text-warn-800">
                              overrode to {t.diagnosis.gate.final_action} ({t.diagnosis.gate.rule})
                            </span>
                          )}{" "}
                          · logged, not executed
                        </div>
                      </div>
                    )}
                    {t.measurements && (
                      <div className="mt-1 max-w-md text-xs text-ink-600">
                        <span className="mr-1 rounded bg-warn-100 px-1 text-[10px] font-medium uppercase text-warn-900">mock</span>
                        Hardness {t.measurements.hardness_hv} HV · Oxidation {t.measurements.oxidation_mg_cm2} mg/cm² · Composition{" "}
                        {Object.entries(t.measurements.composition_at_pct)
                          .map(([el, v]) => `${el}${v}`)
                          .join("-")}
                        {t.measurement_check && (
                          <div className="mt-0.5">
                            Measurement check:{" "}
                            {t.measurement_check.flags.length === 0 ? (
                              <span className="font-medium text-ok-700">passed</span>
                            ) : (
                              <span className="font-medium text-warn-800">{t.measurement_check.flags.join(", ")}</span>
                            )}
                            {t.measurement_check.checks
                              .filter((k) => !k.passed)
                              .map((k) => (
                                <div key={k.rule} className="text-[11px] text-ink-500">
                                  {k.rule}: {k.detail}
                                </div>
                              ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Pill tone={statusTone(t.status)}>{t.status}</Pill>
                    <span className="text-xs text-ink-500">{t.decision ?? "pending"}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Right: after measuring and release. Release is visible without clicking a sample. */}
      <section className="space-y-4 lg:col-span-3">
        <ColumnHeader title="After measuring and release" />
        <div className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Ready for release</h2>
            <Pill tone={readySamples.length ? "green" : "slate"}>{readySamples.length}</Pill>
          </div>
          {madeSamples.length === 0 ? (
            <p className="mt-2 text-xs text-ink-500">No sample has been made and measured yet. Approve a recipe and it appears here.</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {madeSamples.map((s) => {
                const decided = releasedBy.get(s.sample_id);
                return (
                  <li key={s.sample_id}>
                    <button
                      onClick={() => setReleasePick(s.sample_id)}
                      className={`flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs ring-1 hover:bg-ink-50 ${
                        releaseId === s.sample_id ? "bg-ink-50 ring-ink-400" : "ring-ink-200"
                      }`}
                    >
                      <span>
                        <span className="font-mono text-ink-800">{s.sample_id}</span>
                        <span className="ml-1 font-mono text-[11px] text-ink-500">{s.composition}</span>
                      </span>
                      <Pill tone={decided ? (decided === "release" ? "green" : "red") : "yellow"}>
                        {decided ? (decided === "release" ? "Released" : "Withheld") : s.status ?? "Ready"}
                      </Pill>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {releaseId && (
            <div className="mt-3 border-t border-ink-200 pt-3">
              <ReleaseCard key={releaseId} sampleId={releaseId} role={role} onChange={onChange} />
            </div>
          )}
        </div>

        <div className="rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
          <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">Evidence and lineage</h2>
            <a
              href={phoenixUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-ink-500 underline-offset-2 hover:text-ink-800 hover:underline"
              title="Live runs: project sdl-control-plane. Curated error-analysis examples: sdl-control-plane-seed."
            >
              View Live Trace in Phoenix ↗
            </a>
          </div>
          {sample ? (
            <div className="mt-2 space-y-2 text-xs">
              <div className="font-mono text-ink-800">{sample.sample_id}</div>
              <div>
                Decision: <span className="font-medium">{sample.decision ?? "pending"}</span>
              </div>
              {sample.intuition_note && <div className="italic text-ink-600">&ldquo;{sample.intuition_note}&rdquo;</div>}
              <div className="rounded-md bg-ink-50 p-2 font-mono">
                <div>{sample.receipt.receipt_id}</div>
                <div className="break-all text-[11px] text-ink-500">sha256 {sample.receipt.content_sha256}</div>
                <div className="text-[11px] text-ink-500">
                  {sample.receipt.instrument} · {sample.receipt.recorded_at} · {sample.receipt.signed_by}
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-2 text-xs text-ink-500">Select a sample in the triage queue to see its decision receipt.</p>
          )}
        </div>

        <Collapsible title="Actions log" badge={<Pill tone="slate">{campaign?.actions?.length ?? 0}</Pill>}>
          {(campaign?.actions ?? []).length === 0 ? (
            <p className="text-xs text-ink-500">No actions yet. A Yellow or Red sample that was made gets a diagnosis.</p>
          ) : (
            <ul className="space-y-2">
              {(campaign?.actions ?? []).map((a) => (
                <li key={a.action_id} className="text-xs text-ink-700">
                  <span className="font-mono">{a.sample_id}</span>: <span className="font-medium">{a.final_action}</span>
                  {a.gate.allowed ? "" : ` (gate overrode ${a.proposed.action ?? "proposal"}: ${a.gate.rule})`}
                  <div className="text-ink-500">
                    {a.mode === "mock" ? "mock stand-in" : "Claude"} · {a.executed ? "executed" : "not executed (simulated)"} ·{" "}
                    {a.proposed.cause ? `likely ${a.proposed.cause}` : "no valid cause"}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Collapsible>

        <Collapsible title="Span inspector">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-ink-500">{traceLabel}</p>
            <Pill tone="slate">OpenTelemetry, also sent to Phoenix</Pill>
          </div>
          <ul className="mt-2 max-h-72 space-y-0.5 overflow-auto font-mono text-xs">
            {spans.map((s) => (
              <li key={s.span_id}>
                <button
                  onClick={() => setSelectedSpan(s)}
                  style={{ paddingLeft: `${depthOf(s, spanById) * 12}px` }}
                  className={`block w-full rounded px-1 py-0.5 text-left hover:bg-ink-100 ${
                    selectedSpan?.span_id === s.span_id ? "bg-ink-100" : ""
                  }`}
                >
                  {s.name}{" "}
                  {typeof s.attributes.step_type === "string" && (
                    <TypeChip type={s.attributes.step_type} mock={s.attributes.is_mock === true} />
                  )}{" "}
                  <span className="text-ink-400">{s.duration_ms.toFixed(1)}ms</span>
                </button>
              </li>
            ))}
          </ul>
          {selectedSpan && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-ink-900 p-2 text-[11px] text-ink-100">
              {JSON.stringify(selectedSpan.attributes, null, 2)}
            </pre>
          )}
        </Collapsible>
      </section>
    </div>
    </div>
  );
}
