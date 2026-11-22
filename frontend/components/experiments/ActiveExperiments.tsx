"use client";

import { useState } from "react";
import Link from "next/link";
import Chip, { Tone } from "@/components/app/Chip";
import EvidenceInfo from "@/components/app/EvidenceInfo";
import SourceTag from "@/components/app/SourceTag";
import EvidenceLabel from "@/components/EvidenceLabel";
import { SampleRecord } from "@/lib/api";
import { EvidenceKind } from "@/lib/evidence";
import { formatDay } from "@/lib/format";
import { EXPERIMENTS, ExperimentStatus } from "@/lib/seed/internalExperiments";
import { ACTIVE_STATUSES, useStore } from "@/lib/store";

const STATUS: Record<ExperimentStatus, { label: string; tone: Tone }> = {
  planned: { label: "Planned", tone: "ink" },
  running: { label: "Running", tone: "info" },
  measuring: { label: "Measuring", tone: "cite" },
  complete: { label: "Complete", tone: "ok" },
  stopped: { label: "Stopped", tone: "danger" },
};

// One shape for EXAMPLE experiments and LIVE runs from the API.
type Item = {
  id: string;
  source: "live" | "example";
  title: string;
  status: ExperimentStatus;
  started: string;
  owner: string;
  hypothesis: string;
  recipe: string[]; // one line per recipe, shown in monospace
  results: { property: string; value: string; evidence: EvidenceKind; simulated?: boolean }[];
  note?: string;
  pendingRecipes?: number; // planned: how many recipes wait for review
};

function liveItems(
  plans: { thread_id: string; status: string; created_at: string }[],
  samples: (SampleRecord & { thread_id?: string })[],
  goal: string,
): Item[] {
  return plans.map((p) => {
    const mine = samples.filter((s) => s.thread_id === p.thread_id);
    const made = mine.filter((s) => s.measurements);
    const status: ExperimentStatus = p.status === "paused" ? "planned" : p.status === "stopped" ? "stopped" : "complete";
    return {
      id: p.thread_id,
      source: "live",
      title: `Run ${p.thread_id.replace(/^plan-/, "")}`,
      status,
      started: p.created_at,
      owner: "Planned in Add experiment",
      hypothesis: goal,
      recipe: mine.map((s) => `${s.sample_id}  ${s.composition ?? ""}  ${s.processing ?? ""}`.trim()),
      results: made.flatMap((s) => [
        { property: `${s.sample_id} hardness`, value: `${s.measurements!.hardness_hv} HV`, evidence: "measured" as const, simulated: true },
        { property: `${s.sample_id} oxidation`, value: `${s.measurements!.oxidation_mg_cm2} mg/cm²`, evidence: "measured" as const, simulated: true },
      ]),
      note: status === "stopped" ? "Stopped at the target check: the targets were outside the lab limits." : undefined,
      pendingRecipes: status === "planned" ? mine.filter((s) => !s.decision && !s.measurements).length : undefined,
    };
  });
}

function exampleItems(): Item[] {
  return EXPERIMENTS.map((e) => ({
    id: e.id,
    source: "example",
    title: e.title,
    status: e.status,
    started: e.started,
    owner: e.owner,
    hypothesis: e.hypothesis,
    recipe: [`${e.composition}  ${e.route}`],
    results: e.results.map((r) => ({ property: r.property, value: r.value, evidence: r.evidence })),
    note: e.note,
    pendingRecipes: e.status === "planned" ? 3 : undefined,
  }));
}

const PRIMARY = "inline-flex rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-on-accent hover:opacity-90";

function NextCard({ item }: { item: Item }) {
  const follow = `/experiments/new?followup=${encodeURIComponent(item.id)}`;
  const body: Record<ExperimentStatus, { text: string; action: React.ReactNode }> = {
    planned: {
      text: `Review ${item.pendingRecipes ?? "the"} proposed recipe${item.pendingRecipes === 1 ? "" : "s"}.`,
      action: (
        <Link href="/experiments/new" className={PRIMARY}>
          Continue planning
        </Link>
      ),
    },
    running: { text: "Samples are being made.", action: <a href="#results" className={PRIMARY}>View progress</a> },
    measuring: { text: "Samples are made and being measured.", action: <a href="#results" className={PRIMARY}>View progress</a> },
    complete: {
      text: "Results are saved to history, so the next plan can learn from them.",
      action: (
        <Link href={follow} className={PRIMARY}>
          Start a follow up
        </Link>
      ),
    },
    stopped: {
      text: "Stopped before it finished. The reason is below.",
      action: (
        <Link href={follow} className={PRIMARY}>
          Start a follow up
        </Link>
      ),
    },
  };
  const b = body[item.status];
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-ink-50 px-3 py-2 ring-1 ring-ink-200">
      <div className="text-sm text-ink-800">
        <span className="font-semibold">Next:</span> {b.text}
      </div>
      {b.action}
    </div>
  );
}

function Detail({ item }: { item: Item }) {
  return (
    <article data-id={item.id} className="min-w-0 rounded-lg bg-surface p-4 ring-1 ring-ink-200">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="min-w-0 break-words text-base font-semibold text-ink-900">{item.title}</h2>
        <Chip tone={STATUS[item.status].tone}>{STATUS[item.status].label}</Chip>
        <SourceTag kind={item.source} />
      </div>
      <p className="mt-1 break-words text-xs text-ink-600">
        {item.id} · {item.status === "planned" ? "Planned" : "Started"} {formatDay(item.started)} · {item.owner}
      </p>
      <NextCard item={item} />
      <section className="mt-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-600">Hypothesis</h3>
        <p className="break-words text-sm text-ink-800">{item.hypothesis}</p>
      </section>
      <section className="mt-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-600">Recipe</h3>
        {item.recipe.length ? (
          <ul className="space-y-0.5">
            {item.recipe.map((line) => (
              <li key={line} className="break-all font-mono text-sm text-ink-900">
                {line}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-700">No recipe yet.</p>
        )}
      </section>
      <section id="results" className="mt-4">
        <h3 className="mb-1 flex items-center text-xs font-semibold uppercase tracking-wide text-ink-600">
          Results <EvidenceInfo />
        </h3>
        {item.results.length ? (
          <dl className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-1.5 text-sm">
            {item.results.map((r) => (
              <div key={r.property} className="contents">
                <dt className="min-w-0 break-words text-ink-800">{r.property}</dt>
                <dd className="whitespace-nowrap text-right font-mono text-ink-900">{r.value}</dd>
                <dd className="justify-self-end">
                  <EvidenceLabel kind={r.evidence} simulated={r.simulated} />
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-ink-700">No results yet.</p>
        )}
      </section>
      {item.note && <p className="mt-4 border-t border-ink-200 pt-3 text-sm text-ink-800">{item.note}</p>}
    </article>
  );
}

export default function ActiveExperiments() {
  const { campaign, campaignError } = useStore();
  const [view, setView] = useState<"active" | "done">("active");
  const [selected, setSelected] = useState<string | null>(null);

  const all = [
    ...liveItems(campaign?.plans ?? [], (campaign?.live_samples ?? []) as (SampleRecord & { thread_id?: string })[], campaign?.campaign.goal ?? ""),
    ...exampleItems(),
  ].sort((a, b) => b.started.localeCompare(a.started));
  const isActive = (i: Item) => ACTIVE_STATUSES.includes(i.status);
  const shown = all.filter((i) => (view === "active" ? isActive(i) : !isActive(i)));
  const current = shown.find((i) => i.id === selected) ?? shown[0] ?? null;

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="View" className="flex gap-2">
          {(["active", "done"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={`rounded-full px-3 py-1 text-sm font-medium ring-1 ${
                view === v ? "bg-ink-200 text-ink-900 ring-ink-500" : "bg-surface text-ink-700 ring-ink-500 hover:bg-ink-50"
              }`}
            >
              {v === "active" ? "Active" : "Done"} <span className="text-ink-600">{all.filter((i) => (v === "active") === isActive(i)).length}</span>
            </button>
          ))}
        </div>
        <Link href="/experiments/new" className={PRIMARY}>
          + Add experiment
        </Link>
      </div>
      <p className="mt-2 text-xs text-ink-600">Active: planned, running, measuring. Done: complete, stopped.</p>
      {campaignError && <p className="mt-2 text-sm text-ink-700">{campaignError}</p>}

      {shown.length === 0 ? (
        <p className="mt-6 text-sm text-ink-700">No experiments here yet.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-start">
          <ul className="min-w-0 space-y-2" aria-label="Experiments">
            {shown.map((i) => {
              const active = current?.id === i.id;
              return (
                <li key={i.id}>
                  <button
                    data-row={i.id}
                    onClick={() => setSelected(i.id)}
                    aria-current={active ? "true" : undefined}
                    className={`w-full rounded-lg bg-surface px-3 py-2 text-left ring-1 ${active ? "ring-2 ring-ink-900" : "ring-ink-200 hover:ring-ink-500"}`}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="min-w-0 break-words font-medium text-ink-900">{i.title}</span>
                      <Chip tone={STATUS[i.status].tone}>{STATUS[i.status].label}</Chip>
                      <SourceTag kind={i.source} />
                    </div>
                    <div className="mt-0.5 text-xs text-ink-600">
                      {i.id} · {formatDay(i.started)}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="min-w-0 lg:sticky lg:top-4">{current && <Detail key={current.id} item={current} />}</div>
        </div>
      )}
    </section>
  );
}
