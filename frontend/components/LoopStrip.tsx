"use client";

// The loop at a glance. This strip is the only place stages are numbered; the columns below are named by what they do.
// A star marks the three checkpoints where code or a person can stop a batch.

export const LOOP_STAGES: { label: string; checkpoint?: boolean }[] = [
  { label: "Targets" },
  { label: "Setup agent" },
  { label: "Optimizer and prediction" },
  { label: "Safety gate", checkpoint: true },
  { label: "Scientist review" },
  { label: "Make and measure" },
  { label: "Measurement check", checkpoint: true },
  { label: "Diagnosis" },
  { label: "Save and learn" },
  { label: "Release", checkpoint: true },
];

export default function LoopStrip({ current }: { current: number }) {
  return (
    <nav aria-label="Loop progress" className="mb-4 overflow-x-auto rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200">
      <ol className="flex min-w-max items-center gap-1 text-xs">
        {LOOP_STAGES.map((stage, i) => {
          const state = i < current ? "done" : i === current ? "current" : "todo";
          const tone =
            state === "current"
              ? "bg-slate-900 text-white ring-slate-900"
              : state === "done"
                ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
                : "bg-slate-50 text-slate-500 ring-slate-200";
          return (
            <li key={stage.label} className="flex items-center gap-1" aria-current={state === "current" ? "step" : undefined}>
              <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 font-medium ring-1 ${tone}`}>
                <span className={state === "current" ? "text-slate-300" : "text-slate-400"}>{i + 1}</span>
                {stage.label}
                {stage.checkpoint && (
                  <span title="Checkpoint" aria-label="checkpoint" className={state === "current" ? "text-amber-300" : "text-amber-500"}>
                    ★
                  </span>
                )}
              </span>
              {i < LOOP_STAGES.length - 1 && (
                <span aria-hidden className="text-slate-300">
                  ›
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-[11px] text-slate-500">★ checkpoint: the batch can be stopped here by code (Safety gate, Measurement check) or by a person (Release).</p>
    </nav>
  );
}
