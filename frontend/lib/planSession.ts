// The current Add experiment run, kept in this browser tab (sessionStorage) so leaving the page and coming back does not
// lose a run that is waiting for review. Read defensively: anything malformed is ignored and removed.
import type { PlanResult } from "@/lib/api";

const KEY = "sdl-current-plan-v1";

export function loadPlan(): PlanResult | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (!p || typeof p.thread_id !== "string" || typeof p.status !== "string" || !Array.isArray(p.candidates)) {
      window.sessionStorage.removeItem(KEY);
      return null;
    }
    return p as PlanResult;
  } catch {
    clearPlan();
    return null;
  }
}

export function savePlan(plan: PlanResult): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(plan));
  } catch {
    // storage full or blocked: the run still works on this page
  }
}

export function clearPlan(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
}

// Reads the API's error body as text, whether it is {"detail": "..."} or plain text.
export async function errorText(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const d = JSON.parse(text).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object") return JSON.stringify(d);
  } catch {
    // not JSON
  }
  return text.slice(0, 200) || `HTTP ${res.status}`;
}

export const ALREADY_DECIDED = "Someone already decided this sample, so your decision was not applied. Showing the latest state.";
