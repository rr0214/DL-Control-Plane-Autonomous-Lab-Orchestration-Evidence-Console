"use client";

// One store for the scientist screens.
//  - EXAMPLE decisions (customer requests, example recipes) and their history live in this browser tab only
//    (sessionStorage). Nothing about them is sent to the backend.
//  - LIVE data is the campaign view from the running API: plans, samples awaiting review, made samples, actions.
// Both tabs' counts are computed here so the header can show them on every page.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { CampaignView, SampleRecord, apiFetch } from "@/lib/api";
import { labCheck, RequestTargets } from "@/lib/labCheck";
import { CUSTOMER_REQUESTS, CustomerRequest } from "@/lib/seed/customerRequests";
import { EXAMPLE_RECIPES, ExampleRecipe } from "@/lib/seed/exampleRecipes";
import { EXPERIMENTS, ExperimentStatus } from "@/lib/seed/internalExperiments";
import { EXAMPLE_SCIENTIST } from "@/lib/settings";

export type ReviewStatus = "needs_review" | "accepted" | "rejected";
export const STATUS_LABEL: Record<ReviewStatus, string> = {
  needs_review: "Needs review",
  accepted: "Accepted",
  rejected: "Rejected",
};

// Status chip colors: Needs review amber, Accepted green, Rejected red.
export const STATUS_TONE: Record<ReviewStatus, "warn" | "ok" | "danger"> = { needs_review: "warn", accepted: "ok", rejected: "danger" };

export type HistoryLine = { from: ReviewStatus | null; to: ReviewStatus; by: string; at: string; detail?: string };

export type RequestState = {
  status: ReviewStatus;
  waitingForCustomer?: { targets: RequestTargets; note: string; at: string }; // adjustments sent, no answer yet
  rejection?: { reason: string; note: string };
  history: HistoryLine[];
};

export type RecipeState = { status: ReviewStatus; note?: string; history: HistoryLine[] };

const STORAGE_KEY = "sdl-review-example-v1";

function initialRequests(): Record<string, RequestState> {
  return Object.fromEntries(
    CUSTOMER_REQUESTS.map((r) => {
      const history: HistoryLine[] = [{ from: null, to: "needs_review", by: "Intake", at: r.received }];
      if (r.start?.status === "rejected") {
        history.push({ from: "needs_review", to: "rejected", by: EXAMPLE_SCIENTIST, at: r.start.at, detail: r.start.reason });
        return [r.id, { status: "rejected", rejection: { reason: r.start.reason, note: r.start.note }, history }];
      }
      if (r.start?.status === "accepted") {
        history.push({ from: "needs_review", to: "accepted", by: EXAMPLE_SCIENTIST, at: r.received.replace(/T.*/, "T16:00:00Z") });
        return [r.id, { status: "accepted", history }];
      }
      return [r.id, { status: "needs_review", history }];
    }),
  );
}

function initialRecipes(): Record<string, RecipeState> {
  return Object.fromEntries(
    EXAMPLE_RECIPES.map((r) => [r.id, { status: "needs_review", history: [{ from: null, to: "needs_review", by: "Safety gate", at: r.flagged }] }]),
  );
}

// Reads the saved example decisions. Anything missing, malformed or from an older shape falls back to the seed.
function load(): { requests: Record<string, RequestState>; recipes: Record<string, RecipeState> } {
  const fresh = { requests: initialRequests(), recipes: initialRecipes() };
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return fresh;
    const saved = JSON.parse(raw);
    const ok = (v: unknown) => !!v && typeof v === "object" && typeof (v as RequestState).status === "string" && Array.isArray((v as RequestState).history);
    for (const id of Object.keys(fresh.requests)) if (ok(saved?.requests?.[id])) fresh.requests[id] = saved.requests[id];
    for (const id of Object.keys(fresh.recipes)) if (ok(saved?.recipes?.[id])) fresh.recipes[id] = saved.recipes[id];
  } catch {
    // blocked or corrupt storage: start from the seed
  }
  return fresh;
}

export type LivePendingRecipe = { sample: SampleRecord & { thread_id?: string }; thread_id: string; created_at: string };

export type ActiveFilter = "active" | "done";
export const ACTIVE_STATUSES: ExperimentStatus[] = ["planned", "running", "measuring"];

type Store = {
  ready: boolean;
  requests: Record<string, RequestState>;
  recipes: Record<string, RecipeState>;
  campaign: CampaignView | null;
  campaignError: string | null;
  reloadCampaign: () => Promise<void>;
  livePending: LivePendingRecipe[];
  setRequest: (id: string, next: Omit<RequestState, "history">, line: Omit<HistoryLine, "at" | "by">) => void;
  setRecipe: (id: string, status: ReviewStatus, note: string) => void;
  resetExamples: () => void;
  needsReviewCount: number;
  activeCount: number;
};

const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState(() => ({ requests: initialRequests(), recipes: initialRecipes() }));
  const [ready, setReady] = useState(false);
  const [campaign, setCampaign] = useState<CampaignView | null>(null);
  const [campaignError, setCampaignError] = useState<string | null>(null);

  useEffect(() => {
    setState(load());
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // storage blocked: decisions still work until the page reloads
    }
  }, [state, ready]);

  const reloadCampaign = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/campaigns/CAMP-014`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      setCampaign(await res.json());
      setCampaignError(null);
    } catch {
      setCampaignError("Cannot reach the API, so LIVE items are not shown. Example items still work.");
    }
  }, []);

  useEffect(() => {
    reloadCampaign();
  }, [reloadCampaign]);

  const livePending = useMemo<LivePendingRecipe[]>(() => {
    if (!campaign) return [];
    const paused = new Map(campaign.plans.filter((p) => p.status === "paused").map((p) => [p.thread_id, p.created_at]));
    return (campaign.live_samples as (SampleRecord & { thread_id?: string })[])
      .filter((s) => s.thread_id && paused.has(s.thread_id) && !s.decision && !s.measurements)
      .map((s) => ({ sample: s, thread_id: s.thread_id!, created_at: paused.get(s.thread_id!)! }));
  }, [campaign]);

  const now = () => new Date().toISOString();

  const setRequest: Store["setRequest"] = (id, next, line) =>
    setState((s) => ({
      ...s,
      requests: {
        ...s.requests,
        [id]: { ...next, history: [...s.requests[id].history, { ...line, by: EXAMPLE_SCIENTIST, at: now() }] },
      },
    }));

  const setRecipe: Store["setRecipe"] = (id, status, note) =>
    setState((s) => ({
      ...s,
      recipes: {
        ...s.recipes,
        [id]: {
          status,
          note,
          history: [...s.recipes[id].history, { from: s.recipes[id].status, to: status, by: EXAMPLE_SCIENTIST, at: now(), detail: note || undefined }],
        },
      },
    }));

  const resetExamples = () => setState({ requests: initialRequests(), recipes: initialRecipes() });

  const needsReviewCount =
    Object.values(state.requests).filter((r) => r.status === "needs_review").length +
    Object.values(state.recipes).filter((r) => r.status === "needs_review").length +
    livePending.length;
  const liveActive = (campaign?.plans ?? []).filter((p) => p.status === "paused").length;
  const activeCount = EXPERIMENTS.filter((e) => ACTIVE_STATUSES.includes(e.status)).length + liveActive;

  return (
    <Ctx.Provider
      value={{
        ready,
        requests: state.requests,
        recipes: state.recipes,
        campaign,
        campaignError,
        reloadCampaign,
        livePending,
        setRequest,
        setRecipe,
        resetExamples,
        needsReviewCount,
        activeCount,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore must be used inside StoreProvider");
  return s;
}

// "Waiting N days". Computed in the browser after the first render, so the server and browser never disagree.
export function useNow(): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(t);
  }, []);
  return now;
}

export function waitingDays(since: string, now: number | null): string {
  if (now === null) return "";
  const days = Math.max(0, Math.floor((now - new Date(since).getTime()) / 86_400_000));
  return days === 0 ? "Waiting less than a day" : `Waiting ${days} day${days === 1 ? "" : "s"}`;
}

export type { CustomerRequest, ExampleRecipe };
export { labCheck };
