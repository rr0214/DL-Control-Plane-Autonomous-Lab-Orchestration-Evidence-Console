"use client";

import { useState } from "react";
import Chip from "@/components/app/Chip";
import SourceTag from "@/components/app/SourceTag";
import RequestDetail from "./RequestDetail";
import { ExampleRecipeDetail, LiveRecipeDetail, liveStatus } from "./RecipeDetail";
import { SampleRecord } from "@/lib/api";
import { formatDay } from "@/lib/format";
import { CUSTOMER_REQUESTS, CustomerRequest } from "@/lib/seed/customerRequests";
import { EXAMPLE_RECIPES, ExampleRecipe } from "@/lib/seed/exampleRecipes";
import { ReviewStatus, STATUS_LABEL, STATUS_TONE, useNow, useStore, waitingDays } from "@/lib/store";

const STATUSES: ReviewStatus[] = ["needs_review", "accepted", "rejected"];

type TypeFilter = "all" | "request" | "recipe";
type Sort = "customers" | "oldest" | "newest";

type Row =
  | { key: string; kind: "request"; status: ReviewStatus; date: string; r: CustomerRequest; replied: boolean; waitingCustomer: boolean }
  | { key: string; kind: "example-recipe"; status: ReviewStatus; date: string; x: ExampleRecipe }
  | { key: string; kind: "live-recipe"; status: ReviewStatus; date: string; s: SampleRecord & { thread_id?: string }; thread: string };

const SELECT = "rounded-lg bg-surface px-2 py-1.5 text-sm text-ink-900 ring-1 ring-ink-500 focus:outline-none focus:ring-2 focus:ring-ink-900";

export default function ReviewQueue() {
  const { requests, recipes, campaign, campaignError } = useStore();
  const now = useNow();
  const [status, setStatus] = useState<ReviewStatus>("needs_review");
  const [type, setType] = useState<TypeFilter>("all");
  const [sort, setSort] = useState<Sort>("customers");
  const [selected, setSelected] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  // Every item, in one list. LIVE recipes are the backend's samples paused for review, or already decided.
  const rows: Row[] = [
    ...CUSTOMER_REQUESTS.map((r): Row => {
      const st = requests[r.id];
      return {
        key: r.id,
        kind: "request",
        status: st.status,
        date: r.received,
        r,
        replied: !!r.reply && st.status === "needs_review" && !st.waitingForCustomer,
        waitingCustomer: !!st.waitingForCustomer && st.status === "needs_review",
      };
    }),
    ...EXAMPLE_RECIPES.map((x): Row => ({ key: x.id, kind: "example-recipe", status: recipes[x.id].status, date: x.flagged, x })),
    ...liveRecipeRows(campaign?.plans ?? [], (campaign?.live_samples ?? []) as (SampleRecord & { thread_id?: string })[]),
  ];

  const byDate = (a: Row, b: Row) => a.date.localeCompare(b.date);
  const rank = (row: Row) => (row.kind === "request" ? (row.replied ? 0 : 1) : 2); // replies on top, then customers, then recipes
  const sorted = [...rows].sort(
    sort === "customers" ? (a, b) => rank(a) - rank(b) || byDate(a, b) : sort === "oldest" ? byDate : (a, b) => byDate(b, a),
  );
  const shown = sorted.filter(
    (row) => row.status === status && (type === "all" || (type === "request" ? row.kind === "request" : row.kind !== "request")),
  );
  const current = shown.find((row) => row.key === selected) ?? shown[0] ?? null;
  const count = (s: ReviewStatus) => rows.filter((row) => row.status === s).length;

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Status" className="flex flex-wrap gap-2">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              aria-pressed={status === s}
              className={`rounded-full px-3 py-1 text-sm font-medium ring-1 ${
                status === s ? "bg-ink-200 text-ink-900 ring-ink-500" : "bg-surface text-ink-700 ring-ink-500 hover:bg-ink-50"
              }`}
            >
              {STATUS_LABEL[s]} <span className="text-ink-600">{count(s)}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-ink-700">
            Type
            <select value={type} onChange={(e) => setType(e.target.value as TypeFilter)} className={SELECT}>
              <option value="all">All types</option>
              <option value="request">Customer requests</option>
              <option value="recipe">Recipes</option>
            </select>
          </label>
          <label className="flex items-center gap-1 text-xs text-ink-700">
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className={SELECT}>
              <option value="customers">Customers first, oldest first</option>
              <option value="oldest">Oldest first</option>
              <option value="newest">Newest first</option>
            </select>
          </label>
        </div>
      </div>

      {campaignError && <p className="mt-3 text-sm text-ink-700">{campaignError}</p>}
      {flash && (
        <p role="status" className="mt-3 rounded-md bg-ok-50 px-3 py-2 text-sm text-ok-900 ring-1 ring-ok-200">
          {flash}
        </p>
      )}

      {shown.length === 0 ? (
        <p className="mt-6 text-sm text-ink-700">Nothing here with this status and type.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-start">
          <ul className="min-w-0 space-y-2" aria-label="Items">
            {shown.map((row) => {
              const active = current?.key === row.key;
              return (
                <li key={row.key}>
                  <button
                    data-row={row.key}
                    onClick={() => {
                      setSelected(row.key);
                      setFlash(null);
                    }}
                    aria-current={active ? "true" : undefined}
                    className={`w-full rounded-lg bg-surface px-3 py-2 text-left ring-1 ${active ? "ring-2 ring-ink-900" : "ring-ink-200 hover:ring-ink-500"}`}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className={`min-w-0 font-medium text-ink-900 ${row.kind === "request" ? "" : "font-mono text-sm"}`}>
                        {row.kind === "request" ? row.r.customer : row.kind === "example-recipe" ? row.x.composition : row.s.composition}
                      </span>
                      <Chip tone="ink">{row.kind === "request" ? "Customer request" : "Recipe"}</Chip>
                      <Chip tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Chip>
                      {row.kind === "request" && row.replied && <Chip tone="info">Customer replied</Chip>}
                      {row.kind === "request" && row.waitingCustomer && <Chip tone="ink">Waiting for customer</Chip>}
                      <SourceTag kind={row.kind === "live-recipe" ? "live" : "example"} />
                    </div>
                    <div className="mt-0.5 text-xs text-ink-600">
                      {row.kind === "request" ? row.r.id : row.kind === "example-recipe" ? row.x.id : row.s.sample_id} ·{" "}
                      {row.status === "needs_review" ? waitingDays(row.date, now) || `Since ${formatDay(row.date)}` : formatDay(row.date)}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="min-w-0 lg:sticky lg:top-4">
            {current?.kind === "request" && <RequestDetail key={current.key} request={current.r} />}
            {current?.kind === "example-recipe" && <ExampleRecipeDetail key={current.key} recipe={current.x} />}
            {current?.kind === "live-recipe" && (
              <LiveRecipeDetail key={current.key} sample={current.s} threadId={current.thread} flaggedAt={current.date} onDecided={setFlash} />
            )}
          </div>
        </div>
      )}
    </section>
  );
}

const SCIENTIST_DECISIONS = ["approve", "reject", "revise"];

// LIVE recipes: samples paused for review in a paused run, plus ones a scientist already decided.
function liveRecipeRows(plans: { thread_id: string; status: string; created_at: string }[], samples: (SampleRecord & { thread_id?: string })[]): Row[] {
  const planBy = new Map(plans.map((p) => [p.thread_id, p] as const));
  return samples
    .filter((s) => s.thread_id && planBy.has(s.thread_id))
    // Only scientist decisions count. auto_advance, early_kill and scan_flagged are set by code for samples that never
    // went to review, so they do not belong in the review queue.
    .filter((s) => (s.decision ? SCIENTIST_DECISIONS.includes(s.decision) : planBy.get(s.thread_id!)!.status === "paused" && !s.measurements))
    .map((s) => ({
      key: `live-${s.thread_id}-${s.sample_id}`,
      kind: "live-recipe" as const,
      status: liveStatus(s),
      date: s.decision && s.recorded_at ? s.recorded_at : planBy.get(s.thread_id!)!.created_at,
      s,
      thread: s.thread_id!,
    }));
}
