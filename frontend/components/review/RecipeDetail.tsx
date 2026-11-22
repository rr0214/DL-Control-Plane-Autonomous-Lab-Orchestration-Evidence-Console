"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Chip from "@/components/app/Chip";
import EvidenceInfo from "@/components/app/EvidenceInfo";
import SourceTag from "@/components/app/SourceTag";
import EvidenceLabel from "@/components/EvidenceLabel";
import HistoryList from "./HistoryList";
import { PlanResult, SampleRecord, apiFetch } from "@/lib/api";
import { EvidenceKind } from "@/lib/evidence";
import { REVIEW_DETAIL_ID, focusById } from "@/lib/focus";
import { formatDateTime, formatDay } from "@/lib/format";
import { ALREADY_DECIDED, clearPlan, errorText, loadPlan, savePlan } from "@/lib/planSession";
import { ExampleRecipe } from "@/lib/seed/exampleRecipes";
import { SCIENTIST_ROLE } from "@/lib/settings";
import { ReviewStatus, STATUS_LABEL, STATUS_TONE, useNow, useStore, waitingDays } from "@/lib/store";

const BTN = "rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50";
const INPUT = "mt-1 w-full rounded-md bg-page px-2 py-1 text-sm text-ink-900 ring-1 ring-ink-500 focus:outline-none focus:ring-2 focus:ring-ink-900";

// Revise is not offered: the backend accepts it but holds the recipe exactly like Reject (graph.py), with nothing sent
// back for re-planning. Showing it would promise a revision loop that does not exist.
const REVISE_NOTE = "Revise is not offered: in this build it would hold the recipe exactly like Reject.";

function Properties({ rows }: { rows: { name: string; value: string; evidence: EvidenceKind; simulated?: boolean }[] }) {
  return (
    <section className="mt-4">
      <h3 className="mb-1 flex items-center text-xs font-semibold uppercase tracking-wide text-ink-600">
        Properties <EvidenceInfo />
      </h3>
      <dl className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-1.5 text-sm">
        {rows.map((p) => (
          <div key={p.name} className="contents">
            <dt className="text-ink-800">{p.name}</dt>
            <dd className="whitespace-nowrap text-right font-mono text-ink-900">{p.value}</dd>
            <dd className="justify-self-end">
              <EvidenceLabel kind={p.evidence} simulated={p.simulated} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Decide({
  busy,
  onDecide,
}: {
  busy: boolean;
  onDecide: (decision: "approve" | "reject", note: string) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <section className="mt-4">
      <label className="block text-sm text-ink-800">
        Note <span className="text-ink-600">(optional, saved with the decision)</span>
        <textarea rows={2} maxLength={280} value={note} onChange={(e) => setNote(e.target.value)} className={INPUT} />
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => onDecide("approve", note)} className={`${BTN} bg-ok-700 text-surface hover:bg-ok-800`}>
          Approve
        </button>
        <button disabled={busy} onClick={() => onDecide("reject", note)} className={`${BTN} bg-danger-700 text-surface hover:bg-danger-800`}>
          Reject
        </button>
      </div>
      <p className="mt-1 text-xs text-ink-600">{REVISE_NOTE}</p>
    </section>
  );
}

export function ExampleRecipeDetail({ recipe: x }: { recipe: ExampleRecipe }) {
  const { recipes, setRecipe } = useStore();
  const now = useNow();
  const st = recipes[x.id];
  return (
    <article data-id={x.id} className="min-w-0 rounded-lg bg-surface p-4 ring-1 ring-ink-200">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-base font-semibold text-ink-900">{x.composition}</h2>
        <Chip tone={STATUS_TONE[st.status]}>{STATUS_LABEL[st.status]}</Chip>
        <SourceTag kind="example" />
      </div>
      <p className="mt-1 text-xs text-ink-600">
        {x.id} · {x.route} · {x.campaign} · Flagged {formatDay(x.flagged)}
        {st.status === "needs_review" && now !== null && ` · ${waitingDays(x.flagged, now)}`}
      </p>
      <p className="mt-3 text-sm text-ink-800">{x.gate}</p>
      <p className="mt-1 rounded-md bg-warn-50 px-3 py-2 text-sm text-warn-900 ring-1 ring-warn-200">
        <span className="font-semibold">Why it needs a person:</span> {x.reason}
      </p>
      <Properties rows={x.properties} />
      {st.status === "needs_review" ? (
        <Decide
          busy={false}
          onDecide={(d, note) => {
            setRecipe(x.id, d === "approve" ? "accepted" : "rejected", note);
            focusById(REVIEW_DETAIL_ID);
          }}
        />
      ) : (
        <div className="mt-4 space-y-2">
          {st.note && <p className="text-sm text-ink-800">Note: {st.note}</p>}
          <button
            onClick={() => {
              setRecipe(x.id, "needs_review", "Reopened");
              focusById(REVIEW_DETAIL_ID);
            }} className={`${BTN} bg-surface text-ink-800 ring-1 ring-ink-500 hover:bg-ink-50`}>
            Reopen
          </button>
        </div>
      )}
      <HistoryList lines={st.history} />
    </article>
  );
}

export function liveStatus(s: SampleRecord): ReviewStatus {
  if (!s.decision) return "needs_review";
  return s.decision === "approve" ? "accepted" : "rejected";
}

export function LiveRecipeDetail({
  sample,
  threadId,
  flaggedAt,
  onDecided,
}: {
  sample: SampleRecord;
  threadId: string;
  flaggedAt: string;
  onDecided: (message: string) => void;
}) {
  const { reloadCampaign } = useStore();
  const now = useNow();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = liveStatus(sample);
  // The risk signals for a paused recipe are only in the plan response, which this tab may have kept.
  const [plan, setPlan] = useState<PlanResult | null>(null);
  useEffect(() => setPlan(loadPlan()), [threadId, sample.sample_id]);
  const pending = plan?.thread_id === threadId && plan.pending?.sample_id === sample.sample_id ? plan.pending : null;

  async function decide(decision: "approve" | "reject", note: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/samples/${sample.sample_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Role": SCIENTIST_ROLE },
        body: JSON.stringify({ decision, note }),
      });
      if (res.status === 409) {
        if (plan?.thread_id === threadId) clearPlan();
        setError(ALREADY_DECIDED);
        await reloadCampaign();
        return;
      }
      if (!res.ok) throw new Error(await errorText(res));
      const next: PlanResult = await res.json();
      // Keep the run, decided or not: a decided run has no pending sample, so it cannot be decided twice. It is cleared
      // on a 409 or when a new experiment starts.
      savePlan(next);
      await reloadCampaign();
      onDecided(`${decision === "approve" ? "Approved" : "Rejected"} ${sample.sample_id} (LIVE). Results are in Add experiment.`);
      focusById(REVIEW_DETAIL_ID);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const rows = pending
    ? [
        { name: "Elongation", value: `${pending.risk.predicted_elongation_pct.toFixed(1)}%`, evidence: "predicted" as const },
        { name: "Ductility margin vs Run-071", value: pending.risk.predicted_ductility_margin.toFixed(2), evidence: "predicted" as const },
        { name: "Phase stability", value: `${Math.round(pending.risk.phase_stability * 100)}%`, evidence: "predicted" as const },
        { name: "Furnace blast radius", value: pending.risk.furnace_blast_radius, evidence: "predicted" as const },
      ]
    : [];

  return (
    <article data-id={sample.sample_id} className="min-w-0 rounded-lg bg-surface p-4 ring-1 ring-ink-200">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-base font-semibold text-ink-900">{sample.composition ?? sample.sample_id}</h2>
        <Chip tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Chip>
        <SourceTag kind="live" />
      </div>
      <p className="mt-1 text-xs text-ink-600">
        {sample.sample_id} · {sample.processing} · run {threadId} · Flagged {formatDay(flaggedAt)}
        {status === "needs_review" && now !== null && ` · ${waitingDays(flaggedAt, now)}`}
      </p>
      <p className="mt-3 text-sm text-ink-800">Passed the safety gate: no restricted element, not a repeat of a failed run.</p>
      {pending ? (
        <p className="mt-1 rounded-md bg-warn-50 px-3 py-2 text-sm text-warn-900 ring-1 ring-warn-200">
          <span className="font-semibold">Why it needs a person:</span> {pending.reason} The risk signals come from a mock
          lookup, not a trained model.
        </p>
      ) : (
        <p className="mt-1 text-sm text-ink-700">
          The risk signals for this recipe are kept with the run.{" "}
          <Link href="/experiments/new" className="font-medium underline underline-offset-2">
            Continue in Add experiment
          </Link>{" "}
          to see them, or decide here.
        </p>
      )}
      {rows.length > 0 && <Properties rows={rows} />}
      {status === "needs_review" ? (
        <Decide busy={busy} onDecide={decide} />
      ) : (
        <div className="mt-4 text-sm text-ink-800">
          Decided in the backend{sample.recorded_at ? ` (${formatDateTime(sample.recorded_at)})` : ""}
          {sample.intuition_note ? `. Note: ${sample.intuition_note}` : "."} A backend decision can&apos;t be reopened.
        </div>
      )}
      {error && <p className="mt-2 rounded-md bg-error-50 px-3 py-2 text-sm text-error-800 ring-1 ring-error-200">{error}</p>}
    </article>
  );
}
