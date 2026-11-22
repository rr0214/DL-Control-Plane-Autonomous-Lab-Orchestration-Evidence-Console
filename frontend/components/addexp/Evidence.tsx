"use client";

import { useState } from "react";
import { CampaignView, Literature, PlanResult, SampleRecord, Span, usePhoenixUrl } from "@/lib/api";

// Folded sections. Everything stays available, one click away.
export function Fold({ title, count, children, defaultOpen = false }: { title: string; count?: number; children: React.ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group rounded-lg bg-surface ring-1 ring-ink-200">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2 text-sm font-semibold text-ink-900">
          <span aria-hidden className="text-ink-600 transition-transform group-open:rotate-90">
            ▸
          </span>
          {title}
        </span>
        {count !== undefined && <span className="rounded-full bg-ink-100 px-2 text-xs text-ink-700">{count}</span>}
      </summary>
      <div className="min-w-0 px-4 pb-4 text-sm text-ink-800">{children}</div>
    </details>
  );
}

export function LiteratureList({ items }: { items: Literature[] }) {
  if (!items.length) return <p className="text-ink-700">No references loaded yet.</p>;
  return (
    <ul className="space-y-2">
      {items.map((l) => (
        <li key={l.id} className="min-w-0">
          <a href={l.doi_url} target="_blank" rel="noreferrer" className="font-medium text-info-800 underline-offset-2 hover:underline">
            {l.title}
          </a>
          <div className="text-xs text-ink-600">
            {l.authors} ({l.year}) · {l.venue}
          </div>
          <div className="break-all font-mono text-[11px] text-ink-600">doi:{l.doi}</div>
        </li>
      ))}
    </ul>
  );
}

export function SetupOutput({ plan }: { plan: PlanResult }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-700">
        Setup agent: {plan.literature_mode === "mock" ? "mock reply (no API key or the call failed)" : "Claude"}
      </p>
      {plan.search_space ? (
        <p>
          Search space:{" "}
          {plan.search_space.elements.map((e) => `${e.symbol} ${e.min_pct} to ${e.max_pct}%`).join(", ")}; routes {plan.search_space.routes.join(", ")}
        </p>
      ) : (
        <p className="text-ink-700">No search space (plain lookup), so only the safety tests and the review test ran.</p>
      )}
      {(plan.directions ?? []).length > 0 && (
        <ul className="list-inside list-disc">
          {plan.directions!.map((d) => (
            <li key={d.direction}>
              {d.direction} <span className="text-xs text-ink-600">[{d.cited_ids.join(", ")}]</span>
            </li>
          ))}
        </ul>
      )}
      {plan.notes.length > 0 && (
        <ul className="list-inside list-disc text-xs text-ink-700">
          {plan.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {plan.tool_calls.length > 0 && (
        <div className="text-xs text-ink-700">
          Tool calls:{" "}
          {plan.tool_calls.map((t, i) => (
            <span key={i} className="mr-2 font-mono">
              {t.tool} ({t.transport})
            </span>
          ))}
        </div>
      )}
      {plan.llm_totals && (
        <p className="text-xs text-ink-700">
          LLM calls {plan.llm_totals.calls} · {plan.llm_totals.input_tokens} in / {plan.llm_totals.output_tokens} out tokens ·{" "}
          {plan.llm_totals.cost_usd === null ? "cost n/a" : `$${plan.llm_totals.cost_usd.toFixed(4)}`}
        </p>
      )}
    </div>
  );
}

export function Receipts({ samples }: { samples: SampleRecord[] }) {
  if (!samples.length) return <p className="text-ink-700">No decision receipts for this run yet.</p>;
  return (
    <ul className="space-y-2">
      {samples.map((s) => (
        <li key={s.sample_id} className="min-w-0 rounded-md bg-ink-50 p-2 text-xs ring-1 ring-ink-200">
          <div className="font-mono text-ink-900">
            {s.sample_id} · decision {s.decision ?? "pending"}
          </div>
          {s.intuition_note && <div className="italic text-ink-700">&ldquo;{s.intuition_note}&rdquo;</div>}
          <div className="font-mono text-ink-800">{s.receipt.receipt_id}</div>
          <div className="break-all font-mono text-[11px] text-ink-600">sha256 {s.receipt.content_sha256}</div>
          <div className="text-[11px] text-ink-600">
            {s.receipt.instrument} · {s.receipt.recorded_at} · {s.receipt.signed_by}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Lineage({ plan, samples }: { plan: PlanResult; samples: SampleRecord[] }) {
  const phoenix = usePhoenixUrl();
  return (
    <div className="space-y-2">
      <p>
        Run <span className="font-mono">{plan.thread_id}</span>: {plan.candidates.length} candidates, {plan.verdicts.filter((v) => !v.allowed).length}{" "}
        blocked, {samples.length} sample record{samples.length === 1 ? "" : "s"}. Every step is checkpointed in SQLite and traced.
      </p>
      <a href={phoenix} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-ink-900 underline underline-offset-2">
        Open the traces in Phoenix ↗
      </a>
    </div>
  );
}

export function ActionsLog({ campaign, threadId }: { campaign: CampaignView | null; threadId?: string }) {
  const rows = (campaign?.actions ?? []).filter((a) => !threadId || a.thread_id === threadId);
  if (!rows.length) return <p className="text-ink-700">No actions yet. A Yellow or Red sample that was made gets a diagnosis.</p>;
  return (
    <ul className="space-y-2">
      {rows.map((a) => (
        <li key={a.action_id} className="text-xs text-ink-800">
          <span className="font-mono">{a.sample_id}</span>: <span className="font-medium">{a.final_action}</span>
          {a.gate.allowed ? "" : ` (the gate overrode ${a.proposed.action ?? "the proposal"}: ${a.gate.rule})`}
          <div className="text-ink-600">
            {a.mode === "mock" ? "mock stand-in" : "Claude"} · {a.executed ? "executed" : "not executed (simulated)"} ·{" "}
            {a.proposed.cause ? `likely ${a.proposed.cause}` : "no valid cause"}
          </div>
        </li>
      ))}
    </ul>
  );
}

function depthOf(span: Span, byId: Map<string, Span>): number {
  let depth = 0;
  let parent = span.parent_span_id;
  while (parent && byId.has(parent) && depth < 20) {
    depth += 1;
    parent = byId.get(parent)?.parent_span_id ?? null;
  }
  return depth;
}

export function SpanInspector({ spans }: { spans: Span[] }) {
  const [picked, setPicked] = useState<Span | null>(null);
  const byId = new Map(spans.map((s) => [s.span_id, s] as const));
  if (!spans.length) return <p className="text-ink-700">No spans for this run.</p>;
  return (
    <div>
      <p className="text-xs text-ink-600">OpenTelemetry spans for this run, also sent to Phoenix. Click a span for its attributes.</p>
      <ul className="mt-2 max-h-72 space-y-0.5 overflow-auto font-mono text-xs">
        {spans.map((s) => (
          <li key={s.span_id}>
            <button
              onClick={() => setPicked(s)}
              style={{ paddingLeft: `${depthOf(s, byId) * 12}px` }}
              className={`block w-full rounded px-1 py-0.5 text-left hover:bg-ink-100 ${picked?.span_id === s.span_id ? "bg-ink-100" : ""}`}
            >
              {s.name} <span className="text-ink-600">{s.duration_ms.toFixed(1)}ms</span>
            </button>
          </li>
        ))}
      </ul>
      {picked && (
        <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-ink-50 p-2 text-[11px] text-ink-900 ring-1 ring-ink-200">
          {JSON.stringify(picked.attributes, null, 2)}
        </pre>
      )}
    </div>
  );
}
