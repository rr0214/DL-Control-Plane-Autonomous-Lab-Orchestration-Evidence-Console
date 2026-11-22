"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Chip from "@/components/app/Chip";
import SourceTag from "@/components/app/SourceTag";
import HistoryList from "./HistoryList";
import { REVIEW_DETAIL_ID, focusById } from "@/lib/focus";
import { formatDateTime, formatDay } from "@/lib/format";
import { LAB_LIMITS, RequestTargets, labCheck, suggestAdjustments } from "@/lib/labCheck";
import { CustomerRequest } from "@/lib/seed/customerRequests";
import { STATUS_LABEL, STATUS_TONE, useNow, useStore, waitingDays } from "@/lib/store";

export const REJECT_REASONS = ["Over lab limit", "Material not allowed", "Out of scope", "Other"] as const;

const ROWS: { key: keyof RequestTargets; label: string; unit: string; limit: (t: RequestTargets) => string }[] = [
  { key: "serviceTempC", label: "Min service temperature", unit: "°C", limit: () => `at most ${LAB_LIMITS.maxServiceTempC}` },
  { key: "minYieldStrengthMpa", label: "Min yield", unit: "MPa", limit: () => `at most ${LAB_LIMITS.maxYieldStrengthMpa}` },
  { key: "maxHafniumAtPct", label: "Max hafnium", unit: "at%", limit: () => "not used (recipes are hafnium free)" },
];

const near = (v: number, limit: number) => v <= limit && v >= limit * (1 - LAB_LIMITS.nearLimitMargin);

function rowFlag(key: keyof RequestTargets, v: number) {
  const limit = key === "serviceTempC" ? LAB_LIMITS.maxServiceTempC : key === "minYieldStrengthMpa" ? LAB_LIMITS.maxYieldStrengthMpa : null;
  if (limit === null) return null;
  if (v > limit) return <Chip tone="danger">Over limit</Chip>;
  if (near(v, limit)) return <Chip tone="warn">Within 5%</Chip>;
  return null;
}

function LabCheckTable({ targets }: { targets: RequestTargets }) {
  const suggested = suggestAdjustments(targets);
  const rows = ROWS.filter((r) => r.key !== "maxHafniumAtPct" || targets.maxHafniumAtPct > 0);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-sm">
        <thead>
          <tr className="text-left text-xs text-ink-600">
            <th className="py-1 pr-3 font-medium">Property</th>
            <th className="py-1 pr-3 text-right font-medium">Requested</th>
            <th className="py-1 pr-3 font-medium">Lab limit</th>
            <th className="py-1 pr-3 text-right font-medium">Suggested</th>
            <th className="py-1 font-medium" aria-label="Flag" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-ink-200">
              <td className="py-1.5 pr-3 text-ink-800">
                {r.label} ({r.unit})
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-ink-900">{targets[r.key]}</td>
              <td className="py-1.5 pr-3 text-ink-700">{r.limit(targets)}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-ink-900">{suggested[r.key]}</td>
              <td className="py-1.5">{rowFlag(r.key, targets[r.key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const BTN = "rounded-lg px-3 py-1.5 text-sm font-medium";
const PRIMARY = `${BTN} bg-accent text-on-accent hover:opacity-90`;
const OUTLINE = `${BTN} bg-surface text-ink-800 ring-1 ring-ink-500 hover:bg-ink-50`;
const INPUT = "mt-1 w-full rounded-md bg-page px-2 py-1 text-sm text-ink-900 ring-1 ring-ink-500 focus:outline-none focus:ring-2 focus:ring-ink-900";

function RejectForm({ onDone, onCancel }: { onDone: (reason: string, note: string) => void; onCancel: () => void }) {
  const [reason, setReason] = useState<string>(REJECT_REASONS[0]);
  const [note, setNote] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (note.trim()) onDone(reason, note.trim());
      }}
      className="rounded-lg bg-ink-50 p-3 ring-1 ring-ink-200"
    >
      <fieldset>
        <legend className="text-sm font-semibold text-ink-900">Reason for rejecting</legend>
        <div className="mt-2 grid gap-1 sm:grid-cols-2">
          {REJECT_REASONS.map((r) => (
            <label key={r} className="flex items-center gap-2 text-sm text-ink-800">
              <input type="radio" name="reject-reason" value={r} checked={reason === r} onChange={() => setReason(r)} autoFocus={r === REJECT_REASONS[0]} />
              {r}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="mt-3 block text-sm text-ink-800">
        Note to the customer <span className="text-ink-600">(required, the customer sees it)</span>
        <textarea required rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={INPUT} />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="submit" disabled={!note.trim()} className={`${BTN} bg-danger-700 text-surface hover:bg-danger-800 disabled:opacity-50`}>
          Reject request
        </button>
        <button type="button" onClick={onCancel} className={OUTLINE}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function AdjustForm({
  request,
  onDone,
  onCancel,
}: {
  request: CustomerRequest;
  onDone: (targets: RequestTargets, note: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<RequestTargets>(() => suggestAdjustments(request.targets));
  const [note, setNote] = useState("");
  const check = labCheck(draft);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onDone(draft, note.trim());
      }}
      className="rounded-lg bg-ink-50 p-3 ring-1 ring-ink-200"
    >
      <div className="text-sm font-semibold text-ink-900">Send adjustments</div>
      <p className="text-xs text-ink-600">Prefilled with the suggested values. Change any of them.</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        {ROWS.map((r, i) => (
          <label key={r.key} className="text-xs text-ink-800">
            {r.label} ({r.unit})
            <input
              type="number"
              autoFocus={i === 0}
              min={0}
              step={r.key === "maxHafniumAtPct" ? "0.1" : "1"}
              value={draft[r.key]}
              onChange={(e) => setDraft({ ...draft, [r.key]: Number(e.target.value) })}
              className={`${INPUT} font-mono`}
            />
          </label>
        ))}
      </div>
      <p className="mt-2 text-xs text-ink-700">
        Lab check with these values: <Chip tone={check.status === "ready" ? "ok" : check.status === "change" ? "warn" : "danger"}>{check.label}</Chip>
      </p>
      <label className="mt-2 block text-xs text-ink-800">
        Note to the customer
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={INPUT} />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="submit" className={PRIMARY}>
          Send to customer
        </button>
        <button type="button" onClick={onCancel} className={OUTLINE}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function RequestDetail({ request: r }: { request: CustomerRequest }) {
  const { requests, setRequest } = useStore();
  const now = useNow();
  const st = requests[r.id];
  const [mode, setMode] = useState<"idle" | "reject" | "adjust">("idle");
  const check = labCheck(r.targets);
  const rejectBtn = useRef<HTMLButtonElement>(null);
  const adjustBtn = useRef<HTMLButtonElement>(null);
  const cancelled = useRef<"reject" | "adjust" | null>(null);
  // Cancel returns focus to the button that opened the form.
  useEffect(() => {
    if (mode !== "idle" || !cancelled.current) return;
    (cancelled.current === "reject" ? rejectBtn : adjustBtn).current?.focus();
    cancelled.current = null;
  }, [mode]);
  const cancel = () => {
    cancelled.current = mode === "idle" ? null : mode;
    setMode("idle");
  };
  const decided = () => focusById(REVIEW_DETAIL_ID); // the pressed button is gone; continue from the detail panel
  const reopen = () => {
    setRequest(r.id, { status: "needs_review" }, { from: st.status, to: "needs_review", detail: "Reopened" });
    decided();
  };

  return (
    <article data-id={r.id} className="min-w-0 rounded-lg bg-surface p-4 ring-1 ring-ink-200">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-ink-900">{r.customer}</h2>
        <Chip tone={STATUS_TONE[st.status]}>{STATUS_LABEL[st.status]}</Chip>
        <SourceTag kind="example" />
      </div>
      <p className="mt-1 text-xs text-ink-600">
        {r.id} · Received {formatDay(r.received)}
        {st.status === "needs_review" && now !== null && ` · ${waitingDays(r.received, now)}`}
      </p>

      <section className="mt-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-600">Lab check: {check.label}</h3>
        <LabCheckTable targets={r.targets} />
        {check.notes.length > 0 && <p className="mt-1 text-xs text-ink-700">{check.notes.join(" ")}</p>}
      </section>

      <section className="mt-4">
        {st.status === "needs_review" && mode === "idle" && (
          <>
            {st.waitingForCustomer && (
              <p className="mb-2 rounded-md bg-info-50 px-3 py-2 text-sm text-info-900 ring-1 ring-info-200">
                Adjustments sent {formatDateTime(st.waitingForCustomer.at)}: {st.waitingForCustomer.targets.serviceTempC} °C,{" "}
                {st.waitingForCustomer.targets.minYieldStrengthMpa} MPa. Waiting for the customer.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button ref={adjustBtn} onClick={() => setMode("adjust")} className={PRIMARY}>
                Send adjustments
              </button>
              <button
                onClick={() => {
                  setRequest(r.id, { status: "accepted" }, { from: "needs_review", to: "accepted" });
                  decided();
                }}
                disabled={check.status === "cannot"}
                title={check.status === "cannot" ? "Outside lab limits: send adjustments or reject" : undefined}
                className={`${OUTLINE} disabled:cursor-not-allowed disabled:opacity-50`}
              >
                Accept
              </button>
              <button ref={rejectBtn} onClick={() => setMode("reject")} className={OUTLINE}>
                Reject
              </button>
            </div>
            {check.status === "cannot" && <p className="mt-1 text-xs text-ink-700">Can&apos;t accept as is: outside lab limits.</p>}
          </>
        )}
        {mode === "reject" && (
          <RejectForm
            onCancel={cancel}
            onDone={(reason, note) => {
              setRequest(r.id, { status: "rejected", rejection: { reason, note } }, { from: "needs_review", to: "rejected", detail: reason });
              setMode("idle");
              decided();
            }}
          />
        )}
        {mode === "adjust" && (
          <AdjustForm
            request={r}
            onCancel={cancel}
            onDone={(targets, note) => {
              setRequest(
                r.id,
                { status: "needs_review", waitingForCustomer: { targets, note, at: new Date().toISOString() } },
                { from: "needs_review", to: "needs_review", detail: "Adjustments sent, waiting for the customer" },
              );
              setMode("idle");
              decided();
            }}
          />
        )}
        {st.status === "accepted" && (
          <div className="flex flex-wrap gap-2">
            <Link href={`/experiments/new?from=${r.id}`} className={PRIMARY}>
              Start experiment
            </Link>
            <button onClick={reopen} className={OUTLINE}>
              Reopen
            </button>
          </div>
        )}
        {st.status === "rejected" && st.rejection && (
          <div className="space-y-2">
            <div className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger-900 ring-1 ring-danger-200">
              <div>
                <span className="font-semibold">Reason:</span> {st.rejection.reason}
              </div>
              <div>
                <span className="font-semibold">Note to the customer:</span> {st.rejection.note}
              </div>
            </div>
            <button onClick={reopen} className={OUTLINE}>
              Reopen
            </button>
          </div>
        )}
      </section>

      <section className="mt-5 border-t border-ink-200 pt-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-600">The customer&apos;s request</h3>
        <p className="text-sm text-ink-800">{r.note}</p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium text-ink-600">Priorities</div>
            <ol className="mt-1 list-inside list-decimal text-sm text-ink-800">
              {r.priorities.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ol>
          </div>
          <div>
            <div className="text-xs font-medium text-ink-600">Materials to avoid</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {r.avoid.length ? r.avoid.map((m) => <Chip key={m} tone="ink">{m}</Chip>) : <span className="text-sm text-ink-600">None listed</span>}
            </div>
          </div>
        </div>
        {r.reply && (
          <p className="mt-3 rounded-md bg-ok-50 px-3 py-2 text-sm text-ok-900 ring-1 ring-ok-200">
            <span className="font-semibold">Customer replied {formatDateTime(r.reply.at)}:</span> {r.reply.text}
          </p>
        )}
        <details className="mt-3 rounded-md ring-1 ring-ink-200">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink-800">More from the customer</summary>
          <dl className="space-y-2 px-3 pb-3 text-sm">
            {r.intake.map((qa) => (
              <div key={qa.question}>
                <dt className="text-xs text-ink-600">{qa.question}</dt>
                <dd className="text-ink-800">{qa.answer}</dd>
              </div>
            ))}
          </dl>
        </details>
      </section>

      <HistoryList lines={st.history} />
    </article>
  );
}
