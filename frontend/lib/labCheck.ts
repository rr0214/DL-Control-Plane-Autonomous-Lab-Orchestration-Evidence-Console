// Automatic lab check for an incoming customer request (frontend demo only, no API call).
//
// ILLUSTRATIVE DEMO LIMITS, copied from the backend so the queue and the real loop agree:
//   maxServiceTempC, maxYieldStrengthMpa  <- backend/app/target_check.py (MAX_SERVICE_TEMP_C, MAX_YIELD_STRENGTH_MPA)
//   restrictedElements                    <- backend/app/config.py (RESTRICTED_ELEMENTS)
// If those change in the backend, change them here too. A value exactly at a limit is allowed, as in target_check.py.
// nearLimitMargin is a demo-only rule: a target within 5% under a limit is flagged so a scientist can look first.
export const LAB_LIMITS = {
  maxServiceTempC: 2200,
  maxYieldStrengthMpa: 2000,
  restrictedElements: ["Hf"],
  nearLimitMargin: 0.05,
} as const;

export type RequestTargets = {
  serviceTempC: number; // minimum service temperature, degrees C
  minYieldStrengthMpa: number; // minimum yield strength at room temperature, MPa
  maxHafniumAtPct: number; // most hafnium the customer accepts, atomic percent (0 means none)
};

export type LabCheckStatus = "ready" | "change" | "cannot";

export const LAB_CHECK_LABEL: Record<LabCheckStatus, string> = {
  ready: "Ready to make",
  change: "Needs a change",
  cannot: "Can't make here",
};

export type LabCheckResult = { status: LabCheckStatus; label: string; reasons: string[] };

const near = (limit: number) => limit * (1 - LAB_LIMITS.nearLimitMargin);

export function labCheck(t: RequestTargets): LabCheckResult {
  const { maxServiceTempC: maxT, maxYieldStrengthMpa: maxS } = LAB_LIMITS;
  const cannot: string[] = [];
  const change: string[] = [];

  if (t.serviceTempC > maxT) cannot.push(`Service temperature ${t.serviceTempC} °C is above the ${maxT} °C lab limit.`);
  else if (t.serviceTempC >= near(maxT))
    change.push(`Service temperature ${t.serviceTempC} °C is within 5% of the ${maxT} °C lab limit.`);

  if (t.minYieldStrengthMpa > maxS) cannot.push(`Yield strength ${t.minYieldStrengthMpa} MPa is above the ${maxS} MPa lab limit.`);
  else if (t.minYieldStrengthMpa >= near(maxS))
    change.push(`Yield strength ${t.minYieldStrengthMpa} MPa is within 5% of the ${maxS} MPa lab limit.`);

  if (t.maxHafniumAtPct > 0)
    change.push(`Allows up to ${t.maxHafniumAtPct} at% hafnium, but this lab does not use hafnium. Confirm a hafnium-free recipe.`);

  const status: LabCheckStatus = cannot.length ? "cannot" : change.length ? "change" : "ready";
  return { status, label: LAB_CHECK_LABEL[status], reasons: [...cannot, ...change] };
}

// Targets the lab could take as they are: anything at or past the 5% margin comes down to just under it, and hafnium
// goes to 0. Used to prefill "Send adjustments". Targets already inside every rule are returned unchanged.
export function suggestAdjustments(t: RequestTargets): RequestTargets {
  const cap = (value: number, limit: number) => (value >= near(limit) ? Math.floor(near(limit)) - 1 : value);
  return {
    serviceTempC: cap(t.serviceTempC, LAB_LIMITS.maxServiceTempC),
    minYieldStrengthMpa: cap(t.minYieldStrengthMpa, LAB_LIMITS.maxYieldStrengthMpa),
    maxHafniumAtPct: 0,
  };
}
