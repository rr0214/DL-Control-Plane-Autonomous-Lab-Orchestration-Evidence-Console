import { CHECKPOINT_NOTE, LOOP_STEPS, StepTag } from "@/lib/loopSteps";

const TAG: Record<StepTag, string> = {
  Code: "bg-ink-100 text-ink-800 ring-ink-300",
  "AI agent": "bg-ai-100 text-ai-800 ring-ai-300",
  "ML simulated": "bg-warn-100 text-warn-900 ring-warn-300",
  Simulated: "bg-danger-100 text-danger-800 ring-danger-300",
  Person: "bg-ok-100 text-ok-800 ring-ok-300",
};

// The 10 steps as cards, two rows of five on wide screens. Tags were checked against the code (lib/loopSteps.ts).
// Nothing is called an ML model unless it is one: the optimizer and prediction are a fixed table and a lookup.
export default function WhereAIFits() {
  return (
    <section className="rounded-lg bg-surface p-5 ring-1 ring-ink-200">
      <h2 className="text-lg font-semibold text-ink-900">Where ML and AI fit</h2>
      <p className="mt-1 text-sm text-ink-700">
        Claude does two jobs: it sets up each batch and proposes a diagnosis. Plain code makes every safety decision. People
        decide at review and release. The numeric models are stand-ins today.
      </p>
      <ol className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {LOOP_STEPS.map((s, i) => (
          <li key={s.name} className="flex min-w-0 flex-col rounded-lg bg-page p-3 ring-1 ring-ink-200">
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm font-semibold text-ink-900">
                <span className="mr-1 font-mono text-xs text-ink-600">{i + 1}</span>
                {s.name}
                {s.checkpoint && <span aria-label="checkpoint"> ★</span>}
              </span>
            </div>
            <span className={`mt-2 inline-flex w-fit rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${TAG[s.tag]}`}>{s.tag}</span>
            <p className="mt-2 text-xs text-ink-800">{s.note}</p>
            <p className="mt-auto pt-2 font-mono text-[11px] text-ink-600">{s.where}</p>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-ink-700">★ {CHECKPOINT_NOTE}</p>
    </section>
  );
}
