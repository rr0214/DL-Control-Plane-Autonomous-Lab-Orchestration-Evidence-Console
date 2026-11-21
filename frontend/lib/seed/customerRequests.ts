// EXAMPLE DATA ONLY. Fictional customers and requests for the Customer queue view. Nothing here comes from the API
// or a real customer, and nothing is saved. Sorted oldest first by the view, not here.
import type { LabCheckStatus, RequestTargets } from "@/lib/labCheck";

export type CustomerRequest = {
  id: string;
  customer: string;
  received: string; // ISO date and time, UTC
  priorities: string[]; // most important first
  targets: RequestTargets;
  avoid: string[]; // materials the customer does not want in the recipe
  note: string;
  expectedCheck: LabCheckStatus; // what labCheck() should return; kept so the rules can be re-checked, not shown
};

export const CUSTOMER_REQUESTS: CustomerRequest[] = [
  {
    id: "REQ-1041",
    customer: "Northwind Turbines (example)",
    received: "2026-11-16T09:12:00Z",
    priorities: ["Heat resistance", "Strength", "Lead time"],
    targets: { serviceTempC: 1200, minYieldStrengthMpa: 600, maxHafniumAtPct: 0 },
    avoid: ["Cobalt", "Beryllium"],
    note: "Blade root fixture for a land turbine.",
    expectedCheck: "ready",
  },
  {
    id: "REQ-1042",
    customer: "Halcyon Aerospace (example)",
    received: "2026-11-16T14:40:00Z",
    priorities: ["Heat resistance", "Weight", "Cost"],
    targets: { serviceTempC: 2150, minYieldStrengthMpa: 900, maxHafniumAtPct: 0 },
    avoid: ["Nickel"],
    note: "Nozzle insert. Temperature is the hard requirement.",
    expectedCheck: "change",
  },
  {
    id: "REQ-1043",
    customer: "Bluepeak Energy (example)",
    received: "2026-11-17T08:05:00Z",
    priorities: ["Heat resistance", "Corrosion resistance"],
    targets: { serviceTempC: 2400, minYieldStrengthMpa: 700, maxHafniumAtPct: 0 },
    avoid: ["Lead", "Cadmium"],
    note: "Burner liner, continuous duty.",
    expectedCheck: "cannot",
  },
  {
    id: "REQ-1044",
    customer: "Corvid Robotics (example)",
    received: "2026-11-17T16:22:00Z",
    priorities: ["Strength", "Wear resistance", "Lead time"],
    targets: { serviceTempC: 900, minYieldStrengthMpa: 1950, maxHafniumAtPct: 0 },
    avoid: ["Cobalt"],
    note: "Gripper finger for a high-load arm.",
    expectedCheck: "change",
  },
  {
    id: "REQ-1045",
    customer: "Meridian Marine (example)",
    received: "2026-11-18T10:30:00Z",
    priorities: ["Corrosion resistance", "Strength"],
    targets: { serviceTempC: 800, minYieldStrengthMpa: 500, maxHafniumAtPct: 2 },
    avoid: ["Copper"],
    note: "Valve seat. Open to small hafnium additions.",
    expectedCheck: "change",
  },
  {
    id: "REQ-1046",
    customer: "Atlas Forge (example)",
    received: "2026-11-18T13:55:00Z",
    priorities: ["Strength", "Cost"],
    targets: { serviceTempC: 1500, minYieldStrengthMpa: 2300, maxHafniumAtPct: 0 },
    avoid: ["Tungsten"],
    note: "Forging die insert.",
    expectedCheck: "cannot",
  },
  {
    id: "REQ-1047",
    customer: "Sable Tooling (example)",
    received: "2026-11-19T09:48:00Z",
    priorities: ["Lead time", "Strength", "Cost"],
    targets: { serviceTempC: 1100, minYieldStrengthMpa: 800, maxHafniumAtPct: 0 },
    avoid: [],
    note: "Short run of fixture blocks.",
    expectedCheck: "ready",
  },
  {
    id: "REQ-1048",
    customer: "Kestrel Space (example)",
    received: "2026-11-20T07:15:00Z",
    priorities: ["Heat resistance", "Strength", "Weight"],
    targets: { serviceTempC: 2250, minYieldStrengthMpa: 2100, maxHafniumAtPct: 1 },
    avoid: ["Beryllium"],
    note: "Thruster throat, both limits pushed.",
    expectedCheck: "cannot",
  },
];
