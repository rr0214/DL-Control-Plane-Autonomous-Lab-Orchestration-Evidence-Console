"use client";

import { useState } from "react";
import { Targets } from "@/lib/api";
import { SAMPLE_SHEET, SheetResult, parseSheet } from "@/lib/materialsSheet";

export const TARGET_FIELDS: { key: keyof Targets; label: string; step: string }[] = [
  { key: "service_temp_c", label: "Min service temperature (°C)", step: "1" },
  { key: "min_yield_strength_mpa", label: "Min yield (MPa)", step: "1" },
  { key: "max_hafnium_at_pct", label: "Max hafnium (at%)", step: "0.1" },
];

const INPUT = "mt-1 w-full rounded-md bg-page px-2 py-1.5 font-mono text-sm text-ink-900 ring-1 ring-ink-500 focus:outline-none focus:ring-2 focus:ring-ink-900";

// Target properties: typed, or filled from a pasted materials sheet (read in the browser, nothing uploaded).
export default function TargetsCard({
  targets,
  onChange,
  disabled,
}: {
  targets: Targets;
  onChange: (t: Targets) => void;
  disabled: boolean;
}) {
  const [mode, setMode] = useState<"type" | "paste">("type");
  const [sheet, setSheet] = useState("");
  const [report, setReport] = useState<SheetResult | null>(null);

  const fill = (text: string) => {
    const r = parseSheet(text);
    setReport(r);
    onChange({ ...targets, ...r.targets });
  };

  return (
    <section className="rounded-lg bg-surface p-4 ring-1 ring-ink-200">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink-900">Target properties</h2>
        <div role="group" aria-label="How to enter targets" className="flex rounded-lg bg-ink-100 p-0.5 text-sm">
          {(["type", "paste"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={`rounded-md px-3 py-1 font-medium ${mode === m ? "bg-surface text-ink-900 shadow-sm ring-1 ring-ink-300" : "text-ink-700"}`}
            >
              {m === "type" ? "Type properties" : "Paste a sheet"}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-ink-600">Set for this experiment. Type them, or fill them from a materials sheet. Default values are illustrative.</p>

      {mode === "paste" && (
        <div className="mt-3">
          <label className="block text-xs text-ink-800">
            Paste lines of property, value and unit (from a spreadsheet, or separated by commas). Read in this browser only.
            <textarea
              rows={5}
              value={sheet}
              onChange={(e) => setSheet(e.target.value)}
              placeholder={"Min service temperature, 1250, °C\nMin yield, 650, MPa\nMax hafnium, 0, at%"}
              className={`${INPUT} font-mono text-xs`}
            />
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              disabled={disabled || !sheet.trim()}
              onClick={() => fill(sheet)}
              className="rounded-lg bg-surface px-3 py-1.5 text-sm font-medium text-ink-800 ring-1 ring-ink-500 hover:bg-ink-50 disabled:opacity-50"
            >
              Fill the fields
            </button>
            <button
              disabled={disabled}
              onClick={() => {
                setSheet(SAMPLE_SHEET);
                fill(SAMPLE_SHEET);
              }}
              className="rounded-lg bg-surface px-3 py-1.5 text-sm font-medium text-ink-800 ring-1 ring-ink-500 hover:bg-ink-50 disabled:opacity-50"
            >
              Use a sample sheet
            </button>
          </div>
          {report && (
            <div role="status" className="mt-2 text-xs text-ink-800">
              <p>
                Read {report.read.length} line{report.read.length === 1 ? "" : "s"}
                {report.skipped.length ? `, skipped ${report.skipped.length}` : ""}. Check the values below before planning.
              </p>
              {report.skipped.length > 0 && (
                <ul className="mt-1 list-inside list-disc text-ink-700">
                  {report.skipped.map((s) => (
                    <li key={s.line}>
                      <span className="font-mono">{s.line.replace(/\t/g, ", ")}</span>: {s.why}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {TARGET_FIELDS.map((f) => (
          <label key={f.key} className="text-xs text-ink-800">
            {f.label}
            <input
              type="number"
              min={0}
              step={f.step}
              disabled={disabled}
              value={targets[f.key]}
              onChange={(e) => onChange({ ...targets, [f.key]: Number(e.target.value) })}
              className={INPUT}
            />
          </label>
        ))}
      </div>
    </section>
  );
}
