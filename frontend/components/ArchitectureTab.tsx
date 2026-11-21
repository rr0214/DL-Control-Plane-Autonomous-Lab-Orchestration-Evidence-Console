"use client";

import { useEffect, useState } from "react";
import { LoopStep, apiFetch } from "@/lib/api";
import SystemDiagram, { SystemDiagramLegend } from "./SystemDiagram";

type Status = LoopStep["status"];

const STATUS_TONE: Record<Status, string> = {
  Built: "bg-ok-100 text-ok-800",
  Mock: "bg-warn-100 text-warn-900",
  Simulated: "bg-warn-100 text-warn-900",
  "Partly built": "bg-info-100 text-info-900",
  Planned: "bg-ink-100 text-ink-600",
};

const TYPE_TONE: Record<LoopStep["type"], string> = {
  LLM: "bg-ai-100 text-ai-800",
  ML: "bg-warn-100 text-warn-900",
  code: "bg-ink-200 text-ink-800",
  person: "bg-ok-100 text-ok-800",
};

function TypeTag({ type, mock }: { type: LoopStep["type"]; mock: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${TYPE_TONE[type]}`}>
      {type}
      {mock && <span className="rounded bg-surface/70 px-1 text-[10px] uppercase">mock</span>}
    </span>
  );
}

function StatusTag({ status }: { status: Status }) {
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

// The 12 steps of one run, worded exactly like the flow diagram in README.md. Keep the two in sync.
const FLOW: { n: string; name: string; tech: string; tag: string; type: LoopStep["type"]; simulated: boolean }[] = [
  { n: "1", name: "Targets", tech: "Next.js form", tag: "REAL", type: "person", simulated: false },
  { n: "2", name: "Target check", tech: "Python rules", tag: "REAL", type: "code", simulated: false },
  { n: "3", name: "Setup agent", tech: "Claude, one answer tool", tag: "REAL", type: "LLM", simulated: false },
  { n: "4", name: "Optimizer", tech: "fixed table via an MCP tool", tag: "SIMULATED", type: "ML", simulated: true },
  { n: "5", name: "Prediction", tech: "Python lookup with no trained model", tag: "SIMULATED", type: "ML", simulated: true },
  { n: "6", name: "Safety gate", tech: "Python policy kernel", tag: "REAL", type: "code", simulated: false },
  { n: "7", name: "Scientist review", tech: "LangGraph pause where a person decides", tag: "REAL", type: "person", simulated: false },
  { n: "8", name: "Make and test", tech: "Python simulator", tag: "SIMULATED", type: "code", simulated: true },
  { n: "9", name: "Measure check", tech: "Python rules on simulated data", tag: "REAL code", type: "code", simulated: false },
  { n: "10", name: "Diagnosis agent", tech: "Claude with a JSON reply", tag: "REAL", type: "LLM", simulated: false },
  { n: "11", name: "Action gate", tech: "Python that fails closed to hold", tag: "REAL", type: "code", simulated: false },
  { n: "12", name: "Release", tech: "FastAPI plus a receipt where a person signs off", tag: "REAL", type: "person", simulated: false },
  { n: "", name: "Save and learn", tech: "SQLite history with no retraining", tag: "REAL", type: "code", simulated: false },
];

function FlowDiagram() {
  return (
    <ol className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {FLOW.map((s, i) => (
        <li
          key={s.name}
          className={`relative rounded-lg border-2 p-3 ${TYPE_TONE[s.type]} ${
            s.simulated ? "border-dashed border-ink-500" : "border-solid border-transparent"
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <span className="text-sm font-semibold">
              {s.n && <span className="mr-1 font-mono text-xs opacity-70">{s.n}</span>}
              {s.name}
            </span>
            <span className="whitespace-nowrap rounded bg-surface/70 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
              {s.tag}
            </span>
          </div>
          <p className="mt-1 text-xs">{s.tech}</p>
          {i < FLOW.length - 1 && (
            <span aria-hidden className="absolute -right-2 top-1/2 hidden -translate-y-1/2 text-ink-400 lg:block">
              ›
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-xl bg-surface p-4 shadow-sm ring-1 ring-ink-200">
      <summary className="cursor-pointer list-none text-sm font-semibold text-ink-900">
        <span className="mr-2 inline-block transition group-open:rotate-90">▸</span>
        {title}
      </summary>
      <div className="mt-3 text-sm text-ink-700">{children}</div>
    </details>
  );
}

export default function ArchitectureTab() {
  const [mcpMode, setMcpMode] = useState<string | null>(null);
  // The steps come from the backend (app/steps.py), so this table cannot drift from the code.
  const [STEPS, setSteps] = useState<LoopStep[]>([]);

  useEffect(() => {
    apiFetch(`/api/health`, { cache: "no-store" })
      .then((r) => r.json())
      .then((b: { mcp_mode?: string }) => setMcpMode(b.mcp_mode ?? null))
      .catch(() => setMcpMode(null));
    apiFetch(`/api/loop`, { cache: "no-store" })
      .then((r) => r.json())
      .then((b: { steps: LoopStep[] }) => setSteps(b.steps))
      .catch(() => setSteps([]));
  }, []);

  const mcpText =
    mcpMode === "fastmcp"
      ? "Active right now (FastMCP session)."
      : mcpMode === "direct"
        ? "Active right now (direct fallback: the same functions called without the MCP session)."
        : "Checking...";

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-surface p-5 shadow-sm ring-1 ring-ink-200">
        <h2 className="text-lg font-semibold text-ink-900">System architecture</h2>
        <p className="mt-1 text-sm text-ink-600">
          What runs where, how the parts talk, and what is real. Dashed, hatched boxes are simulated or example data.
        </p>
        <div className="mt-4">
          <SystemDiagram />
        </div>
        <SystemDiagramLegend />
      </div>

      <div className="rounded-xl bg-surface p-5 shadow-sm ring-1 ring-ink-200">
        <h2 className="text-lg font-semibold text-ink-900">How a run works, step by step</h2>
        <p className="mt-1 text-sm text-ink-600">
          The AI proposes, plain code decides, and a human approves anything irreversible. Every step is recorded.
        </p>

        <FlowDiagram />

        <p className="mt-3 text-xs text-ink-500">
          Colors: green is a person, purple is an AI agent, yellow is math, gray is code. Dashed means simulated, not real. In step 3, code runs the literature lookup first, then Claude reads it and gives one answer.
        </p>
        <p className="mt-2 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-700 ring-1 ring-ink-200">
          Under every step: LangGraph, SQLite checkpoints, FastAPI, Next.js, MCP tool gateway, Arize Phoenix traces through
          OpenTelemetry, and code evals.
        </p>
      </div>

      <Collapsible title="Step details, read from the backend">
        {/* Wide screens: a table. */}
        <div className="mt-4 hidden overflow-hidden rounded-lg ring-1 ring-ink-200 md:block">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-600">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Step</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">What happens</th>
                <th className="px-3 py-2">Tooling</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {STEPS.map((s) => (
                <tr key={s.n} className="align-top">
                  <td className="px-3 py-3 font-mono text-xs text-ink-500">{s.n}</td>
                  <td className="px-3 py-3 font-semibold text-ink-900">{s.step}</td>
                  <td className="px-3 py-3"><TypeTag type={s.type} mock={s.mock} /></td>
                  <td className="px-3 py-3 text-ink-700">{s.what}</td>
                  <td className="px-3 py-3 text-ink-700">{s.tooling}</td>
                  <td className="px-3 py-3">
                    <StatusTag status={s.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Phones: stacked cards. */}
        <ul className="mt-4 space-y-2 md:hidden">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-lg border border-ink-200 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-ink-900">
                  {s.n}. {s.step}
                </span>
                <span className="flex gap-1">
                  <TypeTag type={s.type} mock={s.mock} />
                  <StatusTag status={s.status} />
                </span>
              </div>
              <p className="mt-1 text-sm text-ink-700">{s.what}</p>
              <p className="mt-1 text-xs text-ink-500">{s.tooling}</p>
            </li>
          ))}
        </ul>

        <p className="mt-3 text-xs text-ink-500">
          LLM is a language model, ML is a numeric model, code is plain deterministic code, person is a human decision. Mock means a stand-in with demo values. Simulated means the readings are generated, not measured. The gate, the
          review pause, the receipts and the tracing are real.
        </p>
      </Collapsible>

      <Collapsible title="What is MCP?">
        <p>
          MCP (Model Context Protocol) is a standard way for an agent or the graph to call tools. Think of a USB standard for AI
          tools: the caller asks for a tool by name, and any tool that follows the standard plugs in. That lets me swap the
          mock optimizer for a real one without changing the setup agent.
        </p>
        <p className="mt-2">
          A tool is a function the model can ask the system to run, such as looking up past failed runs. It is not another
          model. In this build, MCP is {mcpText}
        </p>
      </Collapsible>

      <Collapsible title="Why use an LLM at all, and not just the optimizer?">
        <p>
          A Bayesian optimizer is excellent at tuning numbers inside a defined space. It cannot read a paper or decide to try
          a different processing route because the literature suggests it. The LLM reasons about what to try and why, and
          widens the search space. The optimizer then does the math inside it.
        </p>
      </Collapsible>

      <Collapsible title="Demo vs. real life">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-ink-600">
              <tr>
                <th className="py-1 pr-3"></th>
                <th className="py-1 pr-3">This demo</th>
                <th className="py-1">Real lab</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {[
                ["LLM input", "Goal and run history", "Plus literature, lab schedule and past scientist notes"],
                ["LLM output", "Search space and cited directions", "Plus a rationale a scientist can read"],
                ["Risk model", "Hard-coded lookup", "A trained model"],
                ["Setup agent", "Real Claude call, one answer tool", "Real Claude call"],
                ["Diagnosis agent", "Real Claude call with a JSON reply", "Real Claude call"],
                ["Optimizer", "Simulated: a fixed table", "A real optimizer"],
                ["Prediction model", "Simulated: a lookup with no trained model", "A trained model"],
                ["Lab", "Simulated readings", "Robots, SEM and XRD instruments"],
              ].map(([k, a, b]) => (
                <tr key={k}>
                  <td className="py-2 pr-3 font-medium text-ink-900">{k}</td>
                  <td className="py-2 pr-3">{a}</td>
                  <td className="py-2">{b}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Collapsible>
    </div>
  );
}
