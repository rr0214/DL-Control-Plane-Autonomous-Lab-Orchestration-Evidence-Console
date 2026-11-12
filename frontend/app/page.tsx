"use client";

import { useCallback, useEffect, useState } from "react";
import ArchitectureTab from "@/components/ArchitectureTab";
import ConsoleTab from "@/components/ConsoleTab";
import EvalsTab from "@/components/EvalsTab";
import { API, CampaignView } from "@/lib/api";

const TABS = [
  { id: "console", label: "Lab Control Console" },
  { id: "architecture", label: "System Architecture" },
  { id: "evals", label: "Evals & Golden Dataset" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function Home() {
  const [tab, setTab] = useState<TabId>("console");
  const [campaign, setCampaign] = useState<CampaignView | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [resetting, setResetting] = useState(false);
  const [resetNote, setResetNote] = useState<string | null>(null);

  const loadCampaign = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/campaigns/CAMP-014`, { cache: "no-store" });
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      setCampaign(await res.json());
      setBackendError(null);
    } catch {
      setBackendError(`Cannot reach the API at ${API}. Start it with ./start.sh.`);
    }
  }, []);

  useEffect(() => {
    loadCampaign();
  }, [loadCampaign]);

  async function resetDemo() {
    const ok = window.confirm(
      "Reset CAMP-014? This clears its plans, samples, and LangGraph checkpoints. Seed runs (Run-071, Run-088) stay."
    );
    if (!ok) return;
    setResetting(true);
    setResetNote(null);
    try {
      const res = await fetch(`${API}/api/demo/reset?campaign_id=CAMP-014`, {
        method: "POST",
        headers: { "X-Role": "Scientist (PI)" },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setResetKey((k) => k + 1); // remounts the console so no stale plan stays on screen
      await loadCampaign();
      setResetNote("Demo reset. CAMP-014 is back to its seed state.");
    } catch {
      setResetNote("Reset failed. Check that the API is running.");
    } finally {
      setResetting(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">SDL Control Plane</h1>
          <p className="text-sm text-slate-600">Autonomous Lab Orchestration &amp; Evidence Console</p>
        </div>
        <div className="flex items-center gap-3">
          {resetNote && <span className="text-xs text-slate-600">{resetNote}</span>}
          <button
            onClick={resetDemo}
            disabled={resetting}
            className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm ring-1 ring-slate-300 hover:bg-slate-50 disabled:opacity-50"
          >
            {resetting ? "Resetting..." : "Reset Demo"}
          </button>
        </div>
      </header>

      <nav className="mb-6 flex gap-1 rounded-lg bg-white p-1 shadow-sm ring-1 ring-slate-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition ${
              tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {backendError && (
        <div className="mb-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800 ring-1 ring-rose-200">{backendError}</div>
      )}

      {tab === "console" && <ConsoleTab key={resetKey} campaign={campaign} onChange={loadCampaign} />}
      {tab === "architecture" && <ArchitectureTab />}
      {tab === "evals" && <EvalsTab />}
    </main>
  );
}
