export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
};

export type TriageRecord = {
  sample_id: string;
  candidate_id: string;
  composition: string;
  processing: string;
  status: string;
  telemetry: Telemetry | null; // null when the recipe was held and never synthesized
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

export type PlanResult = {
  status: "paused" | "complete";
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
  recorded_at?: string;
  receipt: Receipt;
};

export type CampaignView = {
  campaign: { campaign_id: string; goal: string; tenant: string; export_control: string };
  rbac: {
    tenant: string;
    export_control: string;
    roles: { role: string; permissions: string[] }[];
    decision_permissions: Record<string, string>;
    principle: string;
  };
  seed_samples: SampleRecord[];
  live_samples: SampleRecord[];
  plans: { thread_id: string; status: string; llm_mode: string | null; created_at: string }[];
  seed_trace: Trace;
  literature: Literature[];
  mcp_mode: string;
};
