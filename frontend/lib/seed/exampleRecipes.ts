// EXAMPLE DATA ONLY. Fictional recipes flagged for scientist review, shown in the Review queue next to any LIVE
// recipe the running backend is holding for review. Decisions on these stay in this browser.
import type { EvidenceKind } from "@/lib/evidence";

export type ExampleRecipe = {
  id: string;
  composition: string;
  route: string;
  flagged: string; // ISO time it was flagged for review
  campaign: string;
  gate: string; // what the safety gate said
  reason: string; // why it still needs a person
  properties: { name: string; value: string; evidence: EvidenceKind }[];
};

export const EXAMPLE_RECIPES: ExampleRecipe[] = [
  {
    id: "RCP-301",
    composition: "Nb48-Ti22-Cr18-Al12",
    route: "Additive/Anneal",
    flagged: "2026-11-18T08:40:00Z",
    campaign: "CAMP-014",
    gate: "Passed the safety gate: no restricted element, not a repeat of a failed run.",
    reason: "Predicted ductility is borderline (margin 0.74, review below 0.80) and the furnace blast radius is high.",
    properties: [
      { name: "Elongation", value: "2.2%", evidence: "predicted" },
      { name: "Oxidation mass gain", value: "3.0 mg/cm²", evidence: "predicted" },
      { name: "Hardness of a similar run", value: "436 HV", evidence: "measured" },
      { name: "Alumina scale forms", value: "above 10 at% Al", evidence: "literature" },
    ],
  },
  {
    id: "RCP-302",
    composition: "Nb44-Ti30-Cr16-Al10",
    route: "Arc-Melt",
    flagged: "2026-11-20T14:10:00Z",
    campaign: "CAMP-014",
    gate: "Passed the safety gate: no restricted element, not a repeat of a failed run.",
    reason: "Phase stability is predicted below 90%, so a second phase may form.",
    properties: [
      { name: "Phase stability", value: "87%", evidence: "predicted" },
      { name: "Density", value: "about 6.6 g/cm³", evidence: "proposed" },
      { name: "Elongation", value: "2.6%", evidence: "predicted" },
    ],
  },
];
