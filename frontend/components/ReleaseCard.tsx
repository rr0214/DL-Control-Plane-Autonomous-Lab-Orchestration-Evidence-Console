"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

// Loop step 11 (a person decides). The comparison and the rules come from the backend; this only shows them.

type Row = { key: string; label: string; requirement: string; value: number; unit: string; passed: boolean; basis: string; margin: number };
type Preview = {
  sample_id: string;
  min_note: number;
  evaluation: {
    comparison: { rows: Row[]; all_met: boolean };
    exceptions: string[];
    needs_note: boolean;
    can_release: boolean;
    blocked_rule: string | null;
  };
  release: { decision: string; note: string; receipt: { receipt_id: string; content_sha256: string; signed_by_role: string; recorded_at: string } } | null;
};

export default function ReleaseCard({ sampleId, role, onChange }: { sampleId: string; role: string; onChange: () => void }) {
  const [data, setData] = useState<Preview | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const res = await fetch(`${API}/api/samples/${sampleId}/release`, { cache: "no-store" });
      setData(res.ok ? await res.json() : null);
    } catch {
      setData(null);
    }
  }

  useEffect(() => {
    setNote("");
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sampleId]);

  async function decide(decision: "release" | "withhold") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/samples/${sampleId}/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Role": role },
        body: JSON.stringify({ decision, note }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const d = body?.detail;
        throw new Error(typeof d === "string" ? d : d?.detail ?? `Error ${res.status}`);
      }
      await load();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return null;
  const ev = data.evaluation;
  const done = data.release;

  return (
    <div className="mt-3 rounded-lg border border-slate-200 p-3 text-xs">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold uppercase tracking-wide text-slate-500">Release check</h3>
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">person</span>
      </div>
      <table className="mt-2 w-full text-left">
        <tbody className="divide-y divide-slate-100">
          {ev.comparison.rows.map((r) => (
            <tr key={r.key}>
              <td className="py-1 pr-2 text-slate-700">
                {r.label}
                <div className="text-[11px] text-slate-400">{r.basis}</div>
              </td>
              <td className="py-1 pr-2 text-slate-600">{r.requirement}</td>
              <td className="py-1 pr-2 font-medium">{r.value} {r.unit}</td>
              <td className={`py-1 font-medium ${r.passed ? "text-emerald-700" : "text-red-700"}`}>{r.passed ? "met" : "missed"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ev.exceptions.length > 0 && (
        <p className="mt-2 text-amber-800">
          Exceptions: {ev.exceptions.join(", ")}. Releasing needs a written reason (at least {data.min_note} characters).
        </p>
      )}
      {!ev.can_release && <p className="mt-2 font-medium text-red-700">Red sample: it cannot be released ({ev.blocked_rule}).</p>}

      {done ? (
        <div className="mt-2 rounded bg-slate-50 p-2 font-mono">
          <div className="font-sans font-medium text-slate-800">
            {done.decision === "release" ? "Released" : "Withheld"} by {done.receipt.signed_by_role}
          </div>
          {done.note && <div className="font-sans italic text-slate-600">&ldquo;{done.note}&rdquo;</div>}
          <div>{done.receipt.receipt_id}</div>
          <div className="break-all text-[11px] text-slate-500">sha256 {done.receipt.content_sha256}</div>
        </div>
      ) : (
        <>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={280}
            rows={2}
            placeholder={ev.needs_note ? "Reason (required to release)" : "Note (optional)"}
            className="mt-2 w-full rounded-md border border-slate-300 p-2 text-sm"
          />
          <div className="mt-2 flex gap-2">
            <button
              disabled={busy || !ev.can_release}
              onClick={() => decide("release")}
              className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-40"
            >
              Release
            </button>
            <button
              disabled={busy}
              onClick={() => decide("withhold")}
              className="rounded-lg bg-slate-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-900 disabled:opacity-40"
            >
              Withhold
            </button>
          </div>
          <p className="mt-1 text-[11px] text-slate-400">Acting as {role}. Strength and temperature are estimates from simulated data.</p>
        </>
      )}
      {error && <p className="mt-2 text-red-700">{error}</p>}
    </div>
  );
}
