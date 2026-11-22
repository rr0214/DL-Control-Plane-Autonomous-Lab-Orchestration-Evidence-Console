"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { SHOW_PROTOTYPE_BANNER } from "@/lib/settings";

// Fired by Add experiment after a run, with the run's llm_mode, so the banner updates without a reload.
export const LLM_MODE_EVENT = "sdl-llm-mode";

// The API does not say whether a key is set, and the backend stays unchanged on this branch. The closest real signal is
// the newest run's llm_mode ("mock" when no key is set or the call failed). Before any run, the default text is shown.
function useMockMode(): boolean {
  const [mock, setMock] = useState(false);
  useEffect(() => {
    apiFetch("/api/usage/summary")
      .then((r) => (r.ok ? r.json() : null))
      .then((b: { plans?: { llm_mode: string | null }[] } | null) => setMock(b?.plans?.[0]?.llm_mode === "mock"))
      .catch(() => {});
    const onMode = (e: Event) => setMock((e as CustomEvent<string>).detail === "mock");
    window.addEventListener(LLM_MODE_EVENT, onMode);
    return () => window.removeEventListener(LLM_MODE_EVENT, onMode);
  }, []);
  return mock;
}

// Sits above everything on every screen. Hidden with SHOW_PROTOTYPE_BANNER in lib/settings.ts.
export default function PrototypeBanner() {
  const mock = useMockMode();
  if (!SHOW_PROTOTYPE_BANNER) return null;
  return (
    <div className="mx-auto max-w-7xl px-4 pt-4">
      <div role="note" className="flex rounded-lg border border-ink-200 bg-surface text-sm text-ink-800">
        <span aria-hidden className="w-1.5 shrink-0 rounded-l-lg bg-accent" />
        <p className="px-3 py-2">
          <span className="hidden sm:inline">
            {mock
              ? "Real working prototype, not a clickable demo. Claude replies are mocked in this mode (no API key is set), plain code runs the safety checks, and a scientist approves. Example data."
              : "Real working prototype, not a clickable demo. Claude runs the setup and diagnosis steps, plain code runs the safety checks, and a scientist approves. Example data."}
          </span>
          <span className="sm:hidden">
            {mock ? "Real working prototype. Claude replies are mocked in this mode. Example data." : "Real working prototype with Claude in the loop. Example data."}
          </span>{" "}
          <Link href="/architecture" className="font-medium text-ink-900 underline underline-offset-2">
            See how it works
          </Link>
        </p>
      </div>
    </div>
  );
}
