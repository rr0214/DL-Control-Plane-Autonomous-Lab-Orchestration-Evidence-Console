// EXAMPLE DATA ONLY. Fictional in-house experiments for the Internal experiments view. Nothing here comes from the
// API or a real lab run, and nothing is saved. Each result says where it comes from with an evidence label.
import type { EvidenceKind } from "@/lib/evidence";

export type ExperimentStatus = "planned" | "running" | "measuring" | "complete" | "stopped";

export type Experiment = {
  id: string;
  title: string;
  hypothesis: string;
  basis?: { text: string; evidence: EvidenceKind }; // why the lab is trying it
  composition: string;
  route: string;
  owner: string;
  status: ExperimentStatus;
  started: string; // ISO date and time, UTC (the planned start for a planned experiment)
  results: { property: string; value: string; evidence: EvidenceKind }[];
  note?: string;
};

export const EXPERIMENTS: Experiment[] = [
  {
    id: "EXP-201",
    title: "More aluminum for oxidation",
    hypothesis: "Raising Al to 12 at% thickens the protective oxide without losing the Run-071 ductility.",
    basis: { text: "Al-containing refractory alloys form a protective alumina scale.", evidence: "literature" },
    composition: "Nb42-Ti28-Cr18-Al12",
    route: "Arc-Melt",
    owner: "Alloy team (example)",
    status: "complete",
    started: "2026-11-10T08:00:00Z",
    results: [
      { property: "Oxidation mass gain", value: "3.1 mg/cm²", evidence: "measured" },
      { property: "Hardness", value: "431 HV", evidence: "measured" },
      { property: "Elongation", value: "2.6%", evidence: "predicted" },
    ],
  },
  {
    id: "EXP-202",
    title: "Additive route for the baseline alloy",
    hypothesis: "Additive build plus anneal matches the arc-melted Run-071 baseline.",
    composition: "Nb40-Ti30-Cr20-Al10",
    route: "Additive/Anneal",
    owner: "Process team (example)",
    status: "measuring",
    started: "2026-11-14T09:30:00Z",
    results: [
      { property: "Hardness", value: "418 HV", evidence: "measured" },
      { property: "Oxidation mass gain", value: "3.6 mg/cm²", evidence: "predicted" },
    ],
    note: "Oxidation test is still running; the value shown is the model's estimate.",
  },
  {
    id: "EXP-203",
    title: "Small silicon addition",
    hypothesis: "3 at% Si helps the oxide scale stick during thermal cycling.",
    basis: { text: "Silicon additions improve scale adhesion in similar alloys.", evidence: "literature" },
    composition: "Nb40-Ti27-Cr18-Al12-Si3",
    route: "Arc-Melt",
    owner: "Alloy team (example)",
    status: "running",
    started: "2026-11-17T10:15:00Z",
    results: [{ property: "Oxidation mass gain", value: "2.8 mg/cm²", evidence: "predicted" }],
  },
  {
    id: "EXP-204",
    title: "Lower niobium to cut weight",
    hypothesis: "Dropping Nb to 35 at% lowers density with only a small hardness loss.",
    composition: "Nb35-Ti32-Cr20-Al13",
    route: "Arc-Melt",
    owner: "Alloy team (example)",
    status: "planned",
    started: "2026-11-24T08:00:00Z",
    results: [
      { property: "Density", value: "about 6.4 g/cm³", evidence: "proposed" },
      { property: "Hardness", value: "405 HV", evidence: "predicted" },
    ],
  },
  {
    id: "EXP-205",
    title: "Slower cooldown for the Run-088 alloy",
    hypothesis: "A slower cooldown stops the cracking seen in Run-088.",
    composition: "Nb50-Ti20-Cr15-Al15",
    route: "Arc-Melt, slow cool",
    owner: "Process team (example)",
    status: "stopped",
    started: "2026-11-12T13:00:00Z",
    results: [{ property: "Cracks", value: "found in 2 of 3 coupons", evidence: "measured" }],
    note: "Stopped by the scientist after the first coupons cracked. Same failure as Run-088.",
  },
  {
    id: "EXP-206",
    title: "More chromium for oxidation",
    hypothesis: "Raising Cr to 22 at% lowers oxidation further than Al alone.",
    composition: "Nb38-Ti28-Cr22-Al12",
    route: "Arc-Melt",
    owner: "Alloy team (example)",
    status: "complete",
    started: "2026-11-06T08:00:00Z",
    results: [
      { property: "Oxidation mass gain", value: "2.9 mg/cm²", evidence: "measured" },
      { property: "Hardness", value: "455 HV", evidence: "measured" },
    ],
  },
];
