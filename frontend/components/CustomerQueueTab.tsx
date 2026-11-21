"use client";

import { useState } from "react";
import {
  ListDetail,
  ListRow,
  PANEL_TONE,
  QueueCard,
  QueueView,
  SectionLabel,
  StatusChip,
  Tone,
  formatDate,
  scrollToTopIfNarrow,
} from "./QueueLayout";
import { LAB_CHECK_LABEL, LAB_LIMITS, LabCheckStatus, RequestTargets, labCheck, suggestAdjustments } from "@/lib/labCheck";
import { CUSTOMER_REQUESTS, CustomerRequest } from "@/lib/seed/customerRequests";

// Customer queue: incoming material requests (example data), each with an automatic lab check. Approve and Send
// adjustments only change what is on screen. Nothing is sent to the API or saved; a reload starts over.

const CHECK_TONE: Record<LabCheckStatus, Tone> = { ready: "ok", change: "warn", cannot: "danger" };

type Decision = { kind: "approved" } | { kind: "adjusted"; targets: RequestTargets; note: string };
type Filter = "all" | LabCheckStatus;

const TARGET_ROWS: { key: keyof RequestTargets; label: string; bound: string; unit: string }[] = [
  { key: "serviceTempC", label: "Service temperature", bound: "at least", unit: "°C" },
  { key: "minYieldStrengthMpa", label: "Yield strength", bound: "at least", unit: "MPa" },
  { key: "maxHafniumAtPct", label: "Hafnium", bound: "at most", unit: "at%" },
];

const NOT_SAVED = "Example only, not saved.";

// Which action is the filled (main) one follows the lab check: Ready to make -> Approve as is; Needs a change and
// Can't make here -> Send adjustments. On Can't make here, Approve as is is disabled.
const BTN_FILLED_APPROVE = "bg-ok-700 text-surface hover:bg-ok-800";
const BTN_FILLED_SEND = "bg-accent text-on-accent hover:opacity-90";
const BTN_OUTLINE = "bg-surface text-ink-800 ring-1 ring-ink-300 hover:bg-ink-50";

function TargetsTable({ targets }: { targets: RequestTargets }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {/* Hafnium only when the customer allows some; 0 is the lab's own rule and needs no row. */}
        {TARGET_ROWS.filter((row) => row.key !== "maxHafniumAtPct" || targets.maxHafniumAtPct > 0).map((row) => (
          <tr key={row.key} className="border-b border-ink-100 last:border-0">
            <td className="py-1 pr-2 text-ink-700">{row.label}</td>
            <td className="py-1 pr-2 text-xs text-ink-500">{row.bound}</td>
            <td className="whitespace-nowrap py-1 text-right font-mono text-ink-900">
              {targets[row.key]} <span className="text-ink-500">{row.unit}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AdjustForm({
  request,
  onSend,
  onCancel,
}: {
  request: CustomerRequest;
  onSend: (targets: RequestTargets, note: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<RequestTargets>(() => suggestAdjustments(request.targets));
  const [note, setNote] = useState("");
  const check = labCheck(draft);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSend(draft, note.trim());
      }}
      className="rounded-lg bg-ink-50 p-3 ring-1 ring-ink-200"
    >
      <SectionLabel>Adjustments to send</SectionLabel>
      <p className="mb-2 text-xs text-ink-600">Prefilled with targets the lab can take as they are. Change any value.</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {TARGET_ROWS.map((row) => (
          <label key={row.key} className="text-xs text-ink-700">
            {row.label} ({row.bound}, {row.unit})
            <input
              type="number"
              step={row.key === "maxHafniumAtPct" ? "0.1" : "1"}
              min={0}
              value={draft[row.key]}
              onChange={(e) => setDraft({ ...draft, [row.key]: Number(e.target.value) })}
              className="mt-1 w-full rounded-md bg-surface px-2 py-1 font-mono text-sm text-ink-900 ring-1 ring-ink-300 focus:outline-none focus:ring-2 focus:ring-ink-900"
            />
          </label>
        ))}
      </div>
      <p className="mt-2 text-xs text-ink-700">
        With these values the lab check says: <StatusChip tone={CHECK_TONE[check.status]}>{check.label}</StatusChip>
      </p>
      <label className="mt-2 block text-xs text-ink-700">
        Note to the customer (optional)
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="For example: we can reach 2089 °C reliably; above that is outside what this lab can make."
          className="mt-1 w-full rounded-md bg-surface px-2 py-1 text-sm text-ink-900 ring-1 ring-ink-300 focus:outline-none focus:ring-2 focus:ring-ink-900"
        />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="submit" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-on-accent hover:opacity-90">
          Send to customer
        </button>
        <button type="button" onClick={onCancel} className="rounded-lg px-3 py-1.5 text-sm font-medium text-ink-700 ring-1 ring-ink-300 hover:bg-surface">
          Cancel
        </button>
        <span className="text-xs text-ink-500">{NOT_SAVED}</span>
      </div>
    </form>
  );
}

function DecisionNote({ decision, onUndo }: { decision: Decision; onUndo: () => void }) {
  const text =
    decision.kind === "approved"
      ? "Approved as is."
      : `Adjustments sent: ${decision.targets.serviceTempC} °C, ${decision.targets.minYieldStrengthMpa} MPa, hafnium at most ${decision.targets.maxHafniumAtPct} at%.` +
        (decision.note ? ` Note: “${decision.note}”` : "");
  return (
    <div className={`flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm ring-1 ${PANEL_TONE[decision.kind === "approved" ? "ok" : "info"]}`}>
      <span>
        {text} <span className="font-medium">{NOT_SAVED}</span>
      </span>
      <button onClick={onUndo} className="text-xs font-medium underline underline-offset-2">
        Undo
      </button>
    </div>
  );
}

export default function CustomerQueueTab() {
  const [filter, setFilter] = useState<Filter>("all");
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const rows = [...CUSTOMER_REQUESTS]
    .sort((a, b) => a.received.localeCompare(b.received)) // oldest first
    .map((r) => ({ request: r, check: labCheck(r.targets) }));
  const count = (s: LabCheckStatus) => rows.filter((r) => r.check.status === s).length;
  const shown = rows.filter((r) => filter === "all" || r.check.status === filter);
  const byId = new Map(rows.map((row) => [row.request.id, row] as const));

  const decide = (id: string, decision: Decision | null) => {
    setDecisions((d) => {
      const next = { ...d };
      if (decision) next[id] = decision;
      else delete next[id];
      return next;
    });
    setEditing(null);
  };

  return (
    <QueueView<Filter>
      title="Customer queue"
      description="Incoming material requests, oldest first. Each one gets an automatic lab check before a scientist looks at it."
      banner={
        <>
          These customers and requests are fictional. Approve and Send adjustments only change this screen; nothing is
          sent or saved. Lab limits are the demo limits from the backend ({LAB_LIMITS.maxServiceTempC} °C,{" "}
          {LAB_LIMITS.maxYieldStrengthMpa} MPa; recipes are always hafnium free).
        </>
      }
      filters={[
        { id: "all", label: "All", count: rows.length },
        { id: "ready", label: LAB_CHECK_LABEL.ready, count: count("ready") },
        { id: "change", label: LAB_CHECK_LABEL.change, count: count("change") },
        { id: "cannot", label: LAB_CHECK_LABEL.cannot, count: count("cannot") },
      ]}
      filter={filter}
      onFilter={setFilter}
    >
      <ListDetail
        ids={shown.map((row) => row.request.id)}
        selectedId={selected}
        onSelect={setSelected}
        empty="No requests with this lab check result."
        renderRow={(id, active) => {
          const { request: r, check } = byId.get(id)!;
          return (
            <ListRow
              id={id}
              active={active}
              onClick={() => {
                setSelected(id);
                scrollToTopIfNarrow();
              }}
              title={r.customer}
              meta={`${r.id} · Received ${formatDate(r.received)}`}
              chip={<StatusChip tone={CHECK_TONE[check.status]}>{check.label}</StatusChip>}
            />
          );
        }}
        renderDetail={(id) => {
          const { request: r, check } = byId.get(id)!;
          const decision = decisions[r.id];
          return (
              <QueueCard
                dataId={r.id}
                title={
                  <>
                    {r.customer} <span className="font-mono text-xs font-normal text-ink-500">{r.id}</span>
                  </>
                }
                subtitle={`Received ${formatDate(r.received)} · ${r.note}`}
                footer={
                  decision ? (
                    <DecisionNote decision={decision} onUndo={() => decide(r.id, null)} />
                  ) : editing === r.id ? (
                    <AdjustForm
                      request={r}
                      onSend={(targets, note) => decide(r.id, { kind: "adjusted", targets, note })}
                      onCancel={() => setEditing(null)}
                    />
                  ) : (
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => decide(r.id, { kind: "approved" })}
                        disabled={check.status === "cannot"}
                        title={check.status === "cannot" ? "Outside lab limits. Send adjustments instead." : undefined}
                        className={`rounded-lg px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${
                          check.status === "ready" ? BTN_FILLED_APPROVE : BTN_OUTLINE
                        }`}
                      >
                        Approve as is
                      </button>
                      <button
                        onClick={() => setEditing(r.id)}
                        className={`rounded-lg px-3 py-1.5 text-sm font-medium ${check.status === "ready" ? BTN_OUTLINE : BTN_FILLED_SEND}`}
                      >
                        Send adjustments
                      </button>
                      {check.status === "cannot" && (
                        <span className="text-xs text-ink-600">Can&apos;t approve as is: outside lab limits.</span>
                      )}
                    </div>
                  )
                }
              >
                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <SectionLabel>Priorities</SectionLabel>
                    <ol className="list-inside list-decimal space-y-0.5 text-sm text-ink-800">
                      {r.priorities.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ol>
                  </div>
                  <div>
                    <SectionLabel>Property targets</SectionLabel>
                    <TargetsTable targets={r.targets} />
                  </div>
                  <div>
                    <SectionLabel>Materials to avoid</SectionLabel>
                    {r.avoid.length ? (
                      <div className="flex flex-wrap gap-1">
                        {r.avoid.map((m) => (
                          <StatusChip key={m} tone="ink">
                            {m}
                          </StatusChip>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-ink-500">None listed</p>
                    )}
                  </div>
                </div>
                <div className={`mt-3 rounded-lg px-3 py-2 text-sm ring-1 ${PANEL_TONE[CHECK_TONE[check.status]]}`}>
                  <span className="font-semibold">Lab check: {check.label}.</span>{" "}
                  {check.reasons.length || check.notes.length
                    ? [...check.reasons, ...check.notes].join(" ")
                    : "All targets are within the lab limits, with no hafnium."}
                </div>
              </QueueCard>
          );
        }}
      />
    </QueueView>
  );
}
