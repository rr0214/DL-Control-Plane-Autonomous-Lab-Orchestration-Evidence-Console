import { useEffect, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Shared access password for a hosted demo (the backend's SDL_ACCESS_PASSWORD). Asked once, kept for this tab in
// sessionStorage, and sent on every API call. When the backend has no password set, none is ever asked for.
const PASSWORD_KEY = "sdl-access-password";
export const AUTH_REQUIRED_EVENT = "sdl-auth-required";
let memoryPassword = ""; // used when sessionStorage is blocked

export function getAccessPassword(): string {
  try {
    return window.sessionStorage.getItem(PASSWORD_KEY) ?? memoryPassword;
  } catch {
    return memoryPassword;
  }
}

export function setAccessPassword(password: string): void {
  memoryPassword = password;
  try {
    if (password) window.sessionStorage.setItem(PASSWORD_KEY, password);
    else window.sessionStorage.removeItem(PASSWORD_KEY);
  } catch {
    // sessionStorage blocked: the in-memory copy still works until the page reloads
  }
}

// Every call to the backend goes through here, so the password header is never forgotten.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const password = typeof window === "undefined" ? "" : getAccessPassword();
  if (password) headers.set("X-Access-Password", password);
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  return res;
}

// Where every "Open trace" link points. The backend reads it from PHOENIX_PUBLIC_URL and reports it on /api/health.
export const DEFAULT_PHOENIX_URL = "http://localhost:6006";

export function usePhoenixUrl(): string {
  const [url, setUrl] = useState(DEFAULT_PHOENIX_URL);
  useEffect(() => {
    apiFetch("/api/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((b: { phoenix_url?: string } | null) => b?.phoenix_url && setUrl(b.phoenix_url))
      .catch(() => {});
  }, []);
  return url;
}

export type Candidate = {
  candidate_id: string;
  composition: string;
  processing: string;
  expected_improvement: number;
  origin?: string;
  source?: string;
};

export type Verdict = {
  candidate_id: string;
  allowed: boolean;
  rule: string | null;
  reason: string;
  latency_ms: number;
};

// Simulated property measurements and the plain-code check on them (loop steps 8 and 9). Mock values.
export type Measurements = {
  mock: boolean;
  instrument: string;
  composition_at_pct: Record<string, number>;
  hardness_hv: number;
  oxidation_mg_cm2: number;
};

export type MeasurementCheck = {
  checks: { rule: string; passed: boolean; detail: string; severity: string | null }[];
  flags: string[];
  severity: "Yellow" | "Red" | null;
  similar: string[];
};

// What the diagnosis agent proposed and what the code gate did with it. Never executed in this prototype.
export type Diagnosis = {
  mode: "anthropic" | "mock";
  executed: boolean;
  gate: {
    allowed: boolean;
    final_action: "re-measure" | "hold";
    rule: string | null;
    detail: string;
    proposal: { action?: string; cause?: string; reason?: string };
  };
};

export type ActionRow = {
  action_id: string;
  thread_id: string;
  sample_id: string;
  final_action: string;
  mode: string;
  executed: boolean;
  created_at: string;
  proposed: { action?: string; cause?: string; reason?: string };
  gate: { allowed: boolean; final_action: string; rule: string | null; detail: string };
};

export type Telemetry = {
  sem_cv_confidence: number;
  xrd_phase_match: number;
  crack_detected: boolean;
};

// Mock pre-synthesis risk signals for a proposed recipe (no sample exists yet).
export type Risk = {
  source: string;
  baseline_run: string;
  predicted_ductility_margin: number;
  ductility_label: string;
  predicted_elongation_pct: number;
  baseline_elongation_pct: number;
  min_elongation_pct: number;
  furnace_blast_radius: string;
  phase_stability: number;
  restricted_elements: string[];
};

export type Pending = {
  stage: string;
  sample_id: string;
  candidate_id: string;
  status: string;
  composition: string;
  processing: string;
  reason: string;
  risk: Risk;
  options: string[];
  origin?: string;
  is_pick?: boolean;
};

export type TargetCheck = {
  feasible: boolean;
  rule: string | null;
  rules: string[];
  reason: string;
};

export type TriageRecord = {
  sample_id: string;
  candidate_id: string;
  composition: string;
  processing: string;
  status: string;
  telemetry: Telemetry | null; // null when the recipe was held and never synthesized
  measurements?: Measurements | null;
  measurement_check?: MeasurementCheck | null;
  diagnosis?: Diagnosis;
  risk?: Risk;
  follow_up?: string | null;
  decision: string | null;
  intuition_note: string;
};

export type Span = {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  start_ms: number;
  duration_ms: number;
  attributes: Record<string, unknown>;
};

export type Trace = { trace_id: string; simulated: boolean; spans: Span[] };

export type ToolCall = {
  tool: string;
  transport: "fastmcp" | "direct";
  args: Record<string, unknown>;
};

export type Literature = {
  id: string;
  title: string;
  authors: string;
  year: number;
  venue: string;
  doi: string;
  doi_url: string;
  topics: string[];
  systems: string[];
  note: string;
  verified_from: string;
};

export type Targets = { service_temp_c: number; min_yield_strength_mpa: number; max_hafnium_at_pct: number };

export type LoopStep = {
  n: number;
  step: string;
  what: string;
  tooling: string;
  type: "LLM" | "ML" | "code" | "person";
  mock: boolean;
  status: "Built" | "Mock" | "Simulated" | "Partly built" | "Planned";
};

export type Direction = { direction: string; cited_ids: string[] };

export type LlmTotals = {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
  models: string[];
};

export type PlanResult = {
  targets?: Targets | null;
  directions?: Direction[];
  literature_mode?: string;
  search_space?: { elements: { symbol: string; min_pct: number; max_pct: number }[]; routes: string[] } | null;
  llm_totals?: LlmTotals;
  status: "paused" | "complete" | "stopped";
  target_check?: TargetCheck | null;
  thread_id: string;
  pending: Pending | null;
  llm_mode: string;
  notes: string[];
  candidates: Candidate[];
  verdicts: Verdict[];
  approved: Candidate[];
  triage: TriageRecord[];
  tool_calls: ToolCall[];
  literature: Literature[];
  mcp_mode: string;
  trace: Trace;
};

export type Receipt = {
  receipt_id: string;
  content_sha256: string;
  instrument: string;
  recorded_at: string;
  signed_by: string;
};

export type SampleRecord = {
  sample_id: string;
  composition?: string;
  processing?: string;
  status?: string;
  decision?: string | null;
  intuition_note?: string;
  telemetry?: Telemetry;
  measurements?: Measurements | null;
  measurement_check?: MeasurementCheck | null;
  recorded_at?: string;
  receipt: Receipt;
};

export type CampaignView = {
  campaign: { campaign_id: string; goal: string; tenant: string; export_control: string; targets?: Targets };
  rbac: {
    tenant: string;
    export_control: string;
    roles: { role: string; permissions: string[] }[];
    decision_permissions: Record<string, string>;
    principle: string;
  };
  seed_samples: SampleRecord[];
  live_samples: SampleRecord[];
  actions?: ActionRow[];
  releases?: { sample_id: string; decision: string; note?: string }[];
  plans: { thread_id: string; status: string; llm_mode: string | null; created_at: string }[];
  seed_trace: Trace;
  literature: Literature[];
  mcp_mode: string;
};
