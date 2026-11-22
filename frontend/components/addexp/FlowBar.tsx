"use client";

import { useState } from "react";
import { CHECKPOINT_NOTE, LOOP_STEPS, PHASES } from "@/lib/loopSteps";

// Four phases with stars on the checkpoints, and an All steps link that opens the 10 steps as a vertical list.
export default function FlowBar({ current }: { current: 1 | 2 | 3 | 4 }) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-label="Experiment flow" className="rounded-lg bg-surface p-3 ring-1 ring-ink-200">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ol className="flex flex-wrap items-center gap-1 text-sm">
          {PHASES.map((p, i) => {
            const state = p.n < current ? "done" : p.n === current ? "current" : "todo";
            return (
              <li key={p.n} className="flex items-center gap-1">
                <span
                  aria-current={state === "current" ? "step" : undefined}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 ring-1 ${
                    state === "current"
                      ? "bg-ink-900 font-medium text-surface ring-ink-900"
                      : state === "done"
                        ? "bg-ok-50 text-ok-900 ring-ok-200"
                        : "bg-ink-50 text-ink-700 ring-ink-200"
                  }`}
                >
                  {p.n} {p.name}
                  {p.checkpoint && <span aria-label="checkpoint">★</span>}
                </span>
                {i < PHASES.length - 1 && <span aria-hidden className="text-ink-500">›</span>}
              </li>
            );
          })}
        </ol>
        <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="text-sm font-medium text-ink-800 underline underline-offset-2">
          {open ? "Hide steps" : "All steps"}
        </button>
      </div>
      {open && (
        <div className="mt-3 border-t border-ink-200 pt-3">
          <ol className="space-y-1.5">
            {LOOP_STEPS.map((s, i) => (
              <li key={s.name} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-2 text-sm">
                <span className="text-right font-mono text-ink-600">{i + 1}</span>
                <span className="min-w-0">
                  <span className="font-medium text-ink-900">
                    {s.name}
                    {s.checkpoint && " ★"}
                  </span>{" "}
                  <span className="text-ink-600">
                    · phase {s.phase} · {s.tag} · {s.note}
                  </span>
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-ink-700">★ {CHECKPOINT_NOTE}</p>
        </div>
      )}
    </section>
  );
}
