"use client";

import { useState } from "react";
import EvidenceLabel from "./EvidenceLabel";
import { ListDetail, ListRow, QueueCard, QueueView, SectionLabel, StatusChip, Tone, formatDate, scrollToTopIfNarrow } from "./QueueLayout";
import { EXPERIMENTS, ExperimentStatus } from "@/lib/seed/internalExperiments";

// Internal experiments: the lab's own experiments (example data), with status and results. Read only. Same layout and
// styles as the Customer queue, through QueueLayout.

const STATUS: Record<ExperimentStatus, { label: string; tone: Tone }> = {
  planned: { label: "Planned", tone: "ink" },
  running: { label: "Running", tone: "info" },
  measuring: { label: "Measuring", tone: "cite" },
  complete: { label: "Complete", tone: "ok" },
  stopped: { label: "Stopped", tone: "danger" },
};
const ORDER: ExperimentStatus[] = ["planned", "running", "measuring", "complete", "stopped"];

type Filter = "all" | ExperimentStatus;

export default function InternalExperimentsTab() {
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const rows = [...EXPERIMENTS].sort((a, b) => b.started.localeCompare(a.started)); // newest first
  const shown = rows.filter((e) => filter === "all" || e.status === filter);
  const byId = new Map(rows.map((e) => [e.id, e] as const));

  return (
    <QueueView<Filter>
      title="Internal experiments"
      description="The lab's own experiments, newest first, with their status and results so far."
      banner={
        <>
          These experiments and results are fictional. Each result is labeled with where it comes from: Measured,
          Predicted, Proposed to test, or From literature.
        </>
      }
      filters={[
        { id: "all", label: "All", count: rows.length },
        ...ORDER.map((s) => ({ id: s, label: STATUS[s].label, count: rows.filter((e) => e.status === s).length })),
      ]}
      filter={filter}
      onFilter={setFilter}
    >
      <ListDetail
        ids={shown.map((e) => e.id)}
        selectedId={selected}
        onSelect={setSelected}
        empty="No experiments with this status."
        renderRow={(id, active) => {
          const e = byId.get(id)!;
          return (
            <ListRow
              id={id}
              active={active}
              onClick={() => {
                setSelected(id);
                scrollToTopIfNarrow();
              }}
              title={e.title}
              meta={`${e.id} · ${e.status === "planned" ? "Planned start" : "Started"} ${formatDate(e.started)}`}
              chip={<StatusChip tone={STATUS[e.status].tone}>{STATUS[e.status].label}</StatusChip>}
            />
          );
        }}
        renderDetail={(id) => {
          const e = byId.get(id)!;
          return (
              <QueueCard
                dataId={e.id}
                title={
                  <>
                    {e.title} <span className="font-mono text-xs font-normal text-ink-500">{e.id}</span>
                  </>
                }
                subtitle={`${e.status === "planned" ? "Planned start" : "Started"} ${formatDate(e.started)} · ${e.owner}`}
                chip={<StatusChip tone={STATUS[e.status].tone}>{STATUS[e.status].label}</StatusChip>}
                footer={e.note ? <p className="text-sm text-ink-700">{e.note}</p> : undefined}
              >
                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <SectionLabel>Hypothesis</SectionLabel>
                    <p className="text-sm text-ink-800">{e.hypothesis}</p>
                    {e.basis && (
                      <p className="mt-2 text-xs text-ink-600">
                        <EvidenceLabel kind={e.basis.evidence} /> {e.basis.text}
                      </p>
                    )}
                  </div>
                  <div>
                    <SectionLabel>Recipe</SectionLabel>
                    <div className="font-mono text-sm text-ink-900">{e.composition}</div>
                    <div className="text-sm text-ink-600">{e.route}</div>
                  </div>
                  <div>
                    <SectionLabel>Results</SectionLabel>
                    <table className="w-full text-sm">
                      <tbody>
                        {e.results.map((r) => (
                          <tr key={r.property} className="border-b border-ink-100 last:border-0">
                            <td className="py-1 pr-2 text-ink-700">{r.property}</td>
                            <td className="whitespace-nowrap py-1 pr-2 text-right font-mono text-ink-900">{r.value}</td>
                            <td className="py-1 text-right">
                              <EvidenceLabel kind={r.evidence} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </QueueCard>
          );
        }}
      />
    </QueueView>
  );
}
