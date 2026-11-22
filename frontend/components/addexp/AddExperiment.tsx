"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Chip from "@/components/app/Chip";
import EvidenceInfo from "@/components/app/EvidenceInfo";
import SourceTag from "@/components/app/SourceTag";
import EvidenceLabel from "@/components/EvidenceLabel";
import ReleaseCard from "@/components/ReleaseCard";
import FlowBar from "./FlowBar";
import TargetsCard from "./TargetsCard";
import { ActionsLog, Fold, LiteratureList, Lineage, Receipts, SetupOutput, SpanInspector } from "./Evidence";
import { Candidate, PlanResult, SampleRecord, Targets, TriageRecord, apiFetch } from "@/lib/api";
import { ALREADY_DECIDED, clearPlan, errorText, loadPlan, savePlan } from "@/lib/planSession";
import { CUSTOMER_REQUESTS } from "@/lib/seed/customerRequests";
import { EXPERIMENTS } from "@/lib/seed/internalExperiments";
import { useStore } from "@/lib/store";

const ROLES = ["Scientist (PI)", "Operator"];
const ORIGIN: Record<string, string> = {
  llm: "Model proposal",
  optimizer: "Optimizer pick, inside the setup agent's search space",
  boundary_probe: "Policy test case (checks the safety gate)",
  yellow_control: "Review test case (forces a scientist review)",
  mock_control: "Review test case (forces a scientist review)",
};
const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "ink"> = { Green: "ok", Yellow: "warn", Red: "danger", Held: "ink" };

const BTN = "rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50";
const PRIMARY = `${BTN} bg-accent text-on-accent hover:opacity-90`;
const OUTLINE = `${BTN} bg-surface text-ink-800 ring-1 ring-ink-500 hover:bg-ink-50`;
const INPUT = "mt-1 w-full rounded-md bg-page px-2 py-1.5 text-sm text-ink-900 ring-1 ring-ink-500 focus:outline-none focus:ring-2 focus:ring-ink-900";

function phaseOf(plan: PlanResult | null, made: number): 1 | 2 | 3 | 4 {
  if (!plan || plan.status === "stopped") return 1;
  if (plan.status === "paused") return 2;
  return made > 0 ? 4 : 3;
}

function RecipeRow({ c, children, open = false, badge }: { c: Candidate; children?: React.ReactNode; open?: boolean; badge: React.ReactNode }) {
  return (
    <details open={open} className="group rounded-md ring-1 ring-ink-200">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="text-ink-600 transition-transform group-open:rotate-90">
          ▸
        </span>
        <span className="min-w-0 break-all font-mono text-sm text-ink-900">{c.composition}</span>
        <span className="text-xs text-ink-600">{c.processing}</span>
        {badge}
      </summary>
      <div className="px-3 pb-3 text-sm text-ink-800">
        <p className="text-xs text-ink-600">
          {c.candidate_id} · {ORIGIN[c.origin ?? ""] ?? c.origin ?? "Proposal"}
        </p>
        {children}
      </div>
    </details>
  );
}

function TriageResults({ rows }: { rows: TriageRecord[] }) {
  if (!rows.length) return <p className="text-ink-700">Nothing was made in this run.</p>;
  return (
    <ul className="space-y-3">
      {rows.map((t) => (
        <li key={t.sample_id} className="min-w-0 rounded-md p-3 ring-1 ring-ink-200">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-ink-900">{t.sample_id}</span>
            <span className="break-all font-mono text-xs text-ink-700">
              {t.composition} · {t.processing}
            </span>
            <Chip tone={STATUS_TONE[t.status] ?? "ink"}>{t.status}</Chip>
            <span className="text-xs text-ink-600">decision {t.decision ?? "pending"}</span>
          </div>
          {t.measurements && (
            <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-1 text-sm">
              {[
                ["Hardness", `${t.measurements.hardness_hv} HV`],
                ["Oxidation mass gain", `${t.measurements.oxidation_mg_cm2} mg/cm²`],
                ["Composition", Object.entries(t.measurements.composition_at_pct).map(([k, v]) => `${k}${v}`).join("-")],
              ].map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-800">{k}</dt>
                  <dd className="whitespace-nowrap text-right font-mono text-ink-900">{v}</dd>
                  <dd className="justify-self-end">
                    <EvidenceLabel kind="measured" simulated />
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {t.measurement_check && t.measurement_check.flags.length > 0 && (
            <p className="mt-2 text-xs text-warn-900">Measurement check flags: {t.measurement_check.flags.join(", ")}</p>
          )}
          {t.diagnosis && (
            <p className="mt-1 text-xs text-ink-800">
              Diagnosis ({t.diagnosis.mode === "mock" ? "mock stand-in" : "Claude"}) proposed {t.diagnosis.gate.proposal.action ?? "nothing valid"}
              ; the code gate decided <span className="font-medium">{t.diagnosis.gate.final_action}</span>
              {t.diagnosis.gate.rule ? ` (${t.diagnosis.gate.rule})` : ""}. Logged, not executed.
            </p>
          )}
          {t.follow_up && <p className="mt-1 text-xs text-ink-700">{t.follow_up}</p>}
        </li>
      ))}
    </ul>
  );
}

export default function AddExperiment() {
  const params = useSearchParams();
  const { campaign, reloadCampaign } = useStore();
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [targets, setTargets] = useState<Targets | null>(null);
  const [goal, setGoal] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [role, setRole] = useState(ROLES[0]);
  const [releasePick, setReleasePick] = useState<string | null>(null);

  // Restore a run this tab was working on, then apply a prefill from the URL (?from=REQ-1042 or ?followup=EXP-201).
  useEffect(() => {
    const saved = loadPlan();
    if (saved) setPlan(saved);
    const from = params.get("from");
    const followup = params.get("followup");
    const req = CUSTOMER_REQUESTS.find((r) => r.id === from);
    if (req) {
      setSource(req.id);
      setGoal(`${req.customer.replace(" (example)", "")}: ${req.note}`);
      setTargets({ service_temp_c: req.targets.serviceTempC, min_yield_strength_mpa: req.targets.minYieldStrengthMpa, max_hafnium_at_pct: req.targets.maxHafniumAtPct });
    } else if (followup) {
      const e = EXPERIMENTS.find((x) => x.id === followup);
      setSource(followup);
      setGoal(e ? `Follow up on ${e.title.toLowerCase()} (${e.id}).` : `Follow up on run ${followup}.`);
    }
  }, [params]);

  const campaignTargets = campaign?.campaign.targets ?? null;
  const activeTargets = targets ?? plan?.targets ?? campaignTargets;
  const shownGoal = goal ?? campaign?.campaign.goal ?? "";
  const threadSamples = ((campaign?.live_samples ?? []) as (SampleRecord & { thread_id?: string })[]).filter((s) => plan && s.thread_id === plan.thread_id);
  const made = threadSamples.filter((s) => s.measurements);
  const released = new Map((campaign?.releases ?? []).map((r) => [r.sample_id, r.decision] as const));
  const releaseId = (releasePick && made.some((s) => s.sample_id === releasePick) ? releasePick : null) ?? made.find((s) => !released.has(s.sample_id))?.sample_id ?? made[0]?.sample_id ?? null;
  const verdictBy = new Map((plan?.verdicts ?? []).map((v) => [v.candidate_id, v] as const));
  const pending = plan?.status === "paused" ? plan.pending : null;
  const reviewCand = pending ? plan!.candidates.find((c) => c.candidate_id === pending.candidate_id) : undefined;
  const autoPass = (plan?.candidates ?? []).filter((c) => verdictBy.get(c.candidate_id)?.allowed && c.candidate_id !== pending?.candidate_id);
  const blocked = (plan?.candidates ?? []).filter((c) => verdictBy.get(c.candidate_id) && !verdictBy.get(c.candidate_id)!.allowed);

  async function runPlan() {
    if (!activeTargets) return;
    setBusy(true);
    setError(null);
    try {
      clearPlan();
      const res = await apiFetch(`/api/campaigns/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: campaign?.campaign.campaign_id ?? "CAMP-014", targets: activeTargets }),
      });
      if (!res.ok) throw new Error(await errorText(res));
      const next: PlanResult = await res.json();
      savePlan(next);
      setPlan(next);
      setNote("");
      await reloadCampaign();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function review(decision: "approve" | "reject") {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/samples/${pending.sample_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Role": role },
        body: JSON.stringify({ decision, note }),
      });
      if (res.status === 409) {
        clearPlan();
        setPlan(null);
        setError(ALREADY_DECIDED);
        await reloadCampaign();
        return;
      }
      if (!res.ok) throw new Error(await errorText(res));
      const next: PlanResult = await res.json();
      savePlan(next); // decided runs stay so the results remain visible; they have no pending sample to decide again
      setPlan(next);
      setNote("");
      await reloadCampaign();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function newExperiment() {
    clearPlan();
    setPlan(null);
    setError(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink-900">Add experiment</h2>
        {plan && (
          <button onClick={newExperiment} className={OUTLINE}>
            Start a new experiment
          </button>
        )}
      </div>

      <FlowBar current={phaseOf(plan, made.length)} />

      <section className="rounded-lg bg-surface p-4 ring-1 ring-ink-200">
        <label className="block text-sm font-semibold text-ink-900" htmlFor="goal">
          Goal
        </label>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-600">
          {source && <Chip tone="info">From {source}</Chip>}
          {source && <SourceTag kind="example" />}
          <span>Your notes for this experiment. The planner works toward the campaign goal; this text is not sent.</span>
        </div>
        <textarea id="goal" rows={2} value={shownGoal} disabled={!!plan} onChange={(e) => setGoal(e.target.value)} className={INPUT} />
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink-800">
          <span className="font-mono">{campaign?.campaign.campaign_id ?? "CAMP-014"}</span>
          <span aria-hidden className="text-ink-500">·</span>
          <span>Tenant {campaign?.campaign.tenant ?? "SDL-Internal"}</span>
          <Chip tone="danger">{campaign?.campaign.export_control ?? "ITAR"}</Chip>
          <SourceTag kind="live" />
          <span className="text-xs text-ink-600">Campaign settings are fixed in this build, so there is no Edit.</span>
        </div>
      </section>

      {activeTargets ? (
        <TargetsCard targets={activeTargets} onChange={setTargets} disabled={!!plan || busy} />
      ) : (
        <p className="text-sm text-ink-700">Loading the campaign from the API...</p>
      )}

      {!plan && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={runPlan} disabled={busy || !activeTargets} className={PRIMARY}>
            {busy ? "Planning..." : "Plan next batch"}
          </button>
          <span className="text-xs text-ink-600">Runs the real loop on the backend: target check, setup agent, optimizer, safety gate.</span>
        </div>
      )}

      {error && <p className="rounded-md bg-error-50 px-3 py-2 text-sm text-error-800 ring-1 ring-error-200">{error}</p>}

      {plan?.status === "stopped" && (
        <section className="rounded-lg bg-danger-50 p-4 text-sm text-danger-900 ring-1 ring-danger-200">
          <div className="flex flex-wrap items-center gap-2 font-semibold">
            Stopped at the target check <SourceTag kind="live" />
          </div>
          <p className="mt-1">{plan.target_check?.reason}</p>
          <p className="mt-1">No recipe was picked and nothing was made. Change the targets in a new experiment.</p>
        </section>
      )}

      {plan && plan.status !== "stopped" && (
        <>
          <section className="space-y-2 rounded-lg bg-surface p-4 ring-1 ring-ink-200">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-ink-900">Proposed batch</h3>
              <SourceTag kind="live" />
              <span className="text-xs text-ink-600">
                {plan.candidates.length} recipes · run <span className="font-mono">{plan.thread_id}</span>
              </span>
            </div>
            {reviewCand && pending && (
              <RecipeRow c={reviewCand} open badge={<Chip tone="warn">Needs your review</Chip>}>
                <p className="mt-2">Passed the safety gate. {pending.reason}</p>
                <h4 className="mb-1 mt-3 flex items-center text-xs font-semibold uppercase tracking-wide text-ink-600">
                  Properties <EvidenceInfo />
                </h4>
                <dl className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-1 text-sm">
                  {[
                    ["Elongation", `${pending.risk.predicted_elongation_pct.toFixed(1)}%`],
                    [`Ductility margin vs ${pending.risk.baseline_run}`, pending.risk.predicted_ductility_margin.toFixed(2)],
                    ["Phase stability", `${Math.round(pending.risk.phase_stability * 100)}%`],
                    ["Furnace blast radius", pending.risk.furnace_blast_radius],
                  ].map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-ink-800">{k}</dt>
                      <dd className="whitespace-nowrap text-right font-mono text-ink-900">{v}</dd>
                      <dd className="justify-self-end">
                        <EvidenceLabel kind="predicted" />
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-1 text-xs text-ink-600">Predicted by a mock lookup ({pending.risk.source}), not a trained model.</p>
                <label className="mt-3 block text-sm">
                  Note <span className="text-ink-600">(optional, saved with the decision)</span>
                  <textarea rows={2} maxLength={280} value={note} onChange={(e) => setNote(e.target.value)} className={INPUT} />
                </label>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <label className="text-xs text-ink-700">
                    Acting as{" "}
                    <select value={role} onChange={(e) => setRole(e.target.value)} className="rounded-md bg-page px-1 py-1 text-xs text-ink-900 ring-1 ring-ink-500">
                      {ROLES.map((r) => (
                        <option key={r}>{r}</option>
                      ))}
                    </select>
                  </label>
                  <button disabled={busy} onClick={() => review("approve")} className={`${BTN} bg-ok-700 text-surface hover:bg-ok-800`}>
                    Approve
                  </button>
                  <button disabled={busy} onClick={() => review("reject")} className={`${BTN} bg-danger-700 text-surface hover:bg-danger-800`}>
                    Reject
                  </button>
                </div>
                <p className="mt-1 text-xs text-ink-600">
                  Revise is not offered: in this build it would hold the recipe exactly like Reject. The server checks the role.
                </p>
              </RecipeRow>
            )}
            {autoPass.map((c) => (
              <RecipeRow key={c.candidate_id} c={c} badge={<Chip tone="ok">Auto pass</Chip>}>
                <p className="mt-1">Passed the safety gate and the risk check, so it goes ahead without a person.</p>
              </RecipeRow>
            ))}
          </section>

          {blocked.length > 0 && (
            <section className="rounded-lg bg-surface p-4 ring-1 ring-ink-200">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-ink-900">Blocked by the safety gate</h3>
                <SourceTag kind="live" />
              </div>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[520px] text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-600">
                      <th className="py-1 pr-3 font-medium">Recipe</th>
                      <th className="py-1 pr-3 font-medium">Route</th>
                      <th className="py-1 pr-3 font-medium">Rule</th>
                      <th className="py-1 font-medium">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blocked.map((c) => {
                      const v = verdictBy.get(c.candidate_id)!;
                      return (
                        <tr key={c.candidate_id} className="border-t border-ink-200 align-top">
                          <td className="py-1.5 pr-3 font-mono text-ink-900">{c.composition}</td>
                          <td className="py-1.5 pr-3 text-ink-800">{c.processing}</td>
                          <td className="py-1.5 pr-3 font-mono text-xs text-danger-800">{v.rule}</td>
                          <td className="py-1.5 text-ink-800">
                            {v.reason}
                            {c.origin === "boundary_probe" && <span className="block text-xs text-ink-600">{ORIGIN.boundary_probe}</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {plan.status === "complete" && (
            <>
              <section className="rounded-lg bg-surface p-4 ring-1 ring-ink-200">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-ink-900">Made and measured</h3>
                  <SourceTag kind="live" />
                  <span className="text-xs text-ink-600">Synthesis and measurement are simulated.</span>
                </div>
                <div className="mt-2">
                  <TriageResults rows={plan.triage} />
                </div>
              </section>
              <section className="rounded-lg bg-surface p-4 ring-1 ring-ink-200">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-ink-900">Release</h3>
                  <SourceTag kind="live" />
                </div>
                {made.length === 0 ? (
                  <p className="mt-2 text-sm text-ink-700">Nothing to release: no sample was made in this run.</p>
                ) : (
                  <>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {made.map((s) => (
                        <button
                          key={s.sample_id}
                          onClick={() => setReleasePick(s.sample_id)}
                          aria-pressed={releaseId === s.sample_id}
                          className={`rounded-full px-3 py-1 text-sm ring-1 ${releaseId === s.sample_id ? "bg-ink-200 text-ink-900 ring-ink-500" : "bg-surface text-ink-700 ring-ink-500"}`}
                        >
                          <span className="font-mono">{s.sample_id}</span>{" "}
                          {released.has(s.sample_id) ? (released.get(s.sample_id) === "release" ? "released" : "withheld") : "ready"}
                        </button>
                      ))}
                    </div>
                    {releaseId && (
                      <div className="mt-3">
                        <ReleaseCard key={releaseId} sampleId={releaseId} role={role} onChange={reloadCampaign} />
                      </div>
                    )}
                  </>
                )}
              </section>
              <Fold title="Decision receipts" count={threadSamples.filter((s) => s.decision).length}>
                <Receipts samples={threadSamples.filter((s) => s.decision)} />
              </Fold>
            </>
          )}

          <Fold title="Evidence and logs">
            <div className="space-y-3">
              <Fold title="Related literature" count={plan.literature.length}>
                <LiteratureList items={plan.literature} />
              </Fold>
              <Fold title="Setup agent output and notes">
                <SetupOutput plan={plan} />
              </Fold>
              <Fold title="Evidence and lineage">
                <Lineage plan={plan} samples={threadSamples} />
              </Fold>
              <Fold title="Actions log" count={(campaign?.actions ?? []).filter((a) => a.thread_id === plan.thread_id).length}>
                <ActionsLog campaign={campaign} threadId={plan.thread_id} />
              </Fold>
              <Fold title="Span inspector" count={plan.trace?.spans.length ?? 0}>
                <SpanInspector spans={plan.trace?.spans ?? []} />
              </Fold>
            </div>
          </Fold>
        </>
      )}
    </div>
  );
}
