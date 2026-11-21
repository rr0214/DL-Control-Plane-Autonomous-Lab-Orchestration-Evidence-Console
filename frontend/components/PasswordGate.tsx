"use client";

import { FormEvent, useEffect, useState } from "react";
import { AUTH_REQUIRED_EVENT, apiFetch, setAccessPassword } from "@/lib/api";

// Shows a small password screen only when the backend asks for one (SDL_ACCESS_PASSWORD is set there).
// Locally there is no password, the first check succeeds, and the app renders as before.
export default function PasswordGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "open" | "locked">("checking");
  const [value, setValue] = useState("");
  const [wrong, setWrong] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch("/api/health")
      .then((r) => setState(r.status === 401 ? "locked" : "open"))
      .catch(() => setState("open")); // backend down: let the page show its own "cannot reach the API" message
    const lock = () => {
      setAccessPassword("");
      setState("locked");
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, lock);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, lock);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setWrong(false);
    setAccessPassword(value);
    try {
      const r = await apiFetch("/api/health");
      if (r.ok) {
        setState("open");
        setValue("");
      } else {
        setAccessPassword("");
        setWrong(true);
        setState("locked");
      }
    } catch {
      setWrong(true);
    } finally {
      setBusy(false);
    }
  }

  if (state === "open") return <>{children}</>;
  if (state === "checking") return null;
  return (
    <main className="mx-auto flex min-h-screen max-w-sm items-center px-4">
      <form onSubmit={submit} className="w-full rounded-xl bg-surface p-6 shadow-sm ring-1 ring-ink-200">
        <h1 className="text-lg font-semibold text-ink-900">SDL Control Plane</h1>
        <p className="mt-1 text-sm text-ink-600">This demo is password protected. Enter the password you were given.</p>
        <label htmlFor="access-password" className="mt-4 block text-sm font-medium text-ink-700">
          Password
        </label>
        <input
          id="access-password"
          type="password"
          autoFocus
          autoComplete="current-password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-ink-300 focus:outline-none focus:ring-2 focus:ring-ink-900"
        />
        {wrong && <p className="mt-2 text-sm text-danger-700">That password did not work. Try again.</p>}
        <button
          type="submit"
          disabled={busy || !value}
          className="mt-4 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Checking..." : "Enter"}
        </button>
      </form>
    </main>
  );
}
