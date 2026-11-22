// Evidence labels: say where a number or a claim comes from. One shared definition, so every screen uses the same
// four words and the same colors. Colors are the --evidence-* tokens in app/tokens.css.

export type EvidenceKind = "measured" | "predicted" | "proposed" | "literature";

export const EVIDENCE: Record<EvidenceKind, { label: string; meaning: string; className: string }> = {
  measured: {
    label: "Measured",
    meaning: "Read from a test of a sample that was made.",
    className: "bg-evidence-measured-bg text-evidence-measured-fg ring-evidence-measured-ring",
  },
  predicted: {
    label: "Predicted",
    meaning: "A model's estimate, before anything is made.",
    className: "bg-evidence-predicted-bg text-evidence-predicted-fg ring-evidence-predicted-ring",
  },
  proposed: {
    label: "Proposed to test",
    meaning: "An idea to try. Nothing has tested it yet.",
    className: "bg-evidence-proposed-bg text-evidence-proposed-fg ring-evidence-proposed-ring",
  },
  literature: {
    label: "From literature",
    meaning: "Reported in a published paper, not measured in this lab.",
    className: "bg-evidence-literature-bg text-evidence-literature-fg ring-evidence-literature-ring",
  },
};

export const EVIDENCE_KINDS = Object.keys(EVIDENCE) as EvidenceKind[];
