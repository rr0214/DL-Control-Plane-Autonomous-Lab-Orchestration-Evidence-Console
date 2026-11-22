import { EVIDENCE, EvidenceKind } from "@/lib/evidence";

// A small tag that says where a value comes from: Measured, Predicted, Proposed to test, or From literature.
// Hovering shows what the label means.
// simulated: a LIVE measured value that came from the simulator (measure.py), shown as "Measured (simulated)".
export default function EvidenceLabel({ kind, simulated = false }: { kind: EvidenceKind; simulated?: boolean }) {
  const e = EVIDENCE[kind];
  return (
    <span
      title={e.meaning}
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${e.className}`}
    >
      {e.label}
      {simulated && " (simulated)"}
    </span>
  );
}
