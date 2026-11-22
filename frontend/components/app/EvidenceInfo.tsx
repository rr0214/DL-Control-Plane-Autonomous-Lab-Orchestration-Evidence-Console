"use client";

import { useState } from "react";
import { EVIDENCE, EVIDENCE_KINDS } from "@/lib/evidence";

// A small info button next to a results heading that explains the evidence labels.
export default function EvidenceInfo() {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="What the evidence labels mean"
        className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold text-ink-700 ring-1 ring-ink-500 hover:bg-ink-50"
      >
        i
      </button>
      {open && (
        <div role="note" className="absolute left-0 z-20 mt-2 w-72 rounded-lg bg-surface p-3 text-xs font-normal normal-case tracking-normal text-ink-800 shadow-md ring-1 ring-ink-300">
          <ul className="space-y-1.5">
            {EVIDENCE_KINDS.map((k) => (
              <li key={k}>
                <span className="font-semibold">{EVIDENCE[k].label}:</span> {EVIDENCE[k].meaning}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-ink-600">In LIVE runs, measured values come from a simulator, so they say Measured (simulated).</p>
        </div>
      )}
    </span>
  );
}
