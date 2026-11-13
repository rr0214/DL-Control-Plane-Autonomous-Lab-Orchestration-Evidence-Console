"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type Status = "Built" | "Mock" | "Simulated" | "Partly built";

type Step = {
  n: number;
  step: string;
  what: string;
  tooling: string;
  status: Status;
};

// One row per step of the loop, in the order a run actually goes. Status is honest about what is real.
const STEPS: Step[] = [
  {
    n: 1,
    step: "Read",
    what: "The planner gets the goal, past runs and literature.",
    tooling: "SQLite run history, curated literature file, MCP tool search_calphad_literature",
    status: "Built",
  },
  {
    n: 2,
    step: "Propose",
    what: "The LLM picks element sets and routes, with a short rationale.",
    tooling: "Claude via tool calling (Anthropic API). Mock plan when no API key is set.",
    status: "Mock",
  },
  {
    n: 3,
    step: "Optimize",
    what: "A numeric optimizer sets the exact percentages. The LLM never writes ratios.",
    tooling: "Bayesian optimizer (fixed table today), called through MCP tool propose_alloy_ratios",
    status: "Mock",
  },
  {
    n: 4,
    step: "Gate",
    what: "Plain code blocks restricted elements and repeats of failed runs.",
    tooling: "Policy Kernel (Python), MCP tool check_negative_runs",
    status: "Built",
  },
  {
    n: 5,
    step: "Score",
    what: "A risk model predicts ductility and phase stability before anything is made.",
    tooling: "Pre-synthesis risk model (hard-coded lookup today)",
    status: "Mock",
  },
  {
    n: 6,
    step: "Review",
    what: "A scientist approves or rejects the recipe and can leave a note.",
    tooling: "LangGraph interrupt() with SQLite checkpoints, role-based access (RBAC), SHA-256 receipts",
    status: "Built",
  },
  {
    n: 7,
    step: "Make and measure",
    what: "A robot makes the sample and scans it.",
    tooling: "Robotic workcell: synthesis robot, SEM and XRD instruments (simulated readings today)",
    status: "Simulated",
  },
  {
    n: 8,
    step: "Learn",
    what: "Failures are found in traces, turned into tests, and fed back.",
    tooling: "OpenTelemetry, Arize Phoenix, golden dataset and experiments, promote_overrides script",
    status: "Partly built",
  },
];

const STATUS_TONE: Record<Status, string> = {
  Built: "bg-emerald-100 text-emerald-800",
  Mock: "bg-amber-100 text-amber-900",
  Simulated: "bg-amber-100 text-amber-900",
  "Partly built": "bg-sky-100 text-sky-900",
};

function StatusTag({ status }: { status: Status }) {
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <summary className="cursor-pointer list-none text-sm font-semibold text-slate-900">
        <span className="mr-2 inline-block transition group-open:rotate-90">▸</span>
        {title}
      </summary>
      <div className="mt-3 text-sm text-slate-700">{children}</div>
    </details>
  );
}

export default function ArchitectureTab() {
  const [mcpMode, setMcpMode] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/health`, { cache: "no-store" })
      .then((r) => r.json())
      .then((b: { mcp_mode?: string }) => setMcpMode(b.mcp_mode ?? null))
      .catch(() => setMcpMode(null));
  }, []);

  const mcpText =
    mcpMode === "fastmcp"
      ? "Active right now (FastMCP session)."
      : mcpMode === "direct"
        ? "Active right now (direct fallback: the same functions called without the MCP session)."
        : "Checking...";

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-lg font-semibold text-slate-900">How a run works, step by step</h2>
        <p className="mt-1 text-sm text-slate-600">
          The AI proposes, plain code decides, and a human approves anything irreversible. Every step is recorded.
        </p>

        {/* Wide screens: a table. */}
        <div className="mt-4 hidden overflow-hidden rounded-lg ring-1 ring-slate-200 md:block">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Step</th>
                <th className="px-3 py-2">What happens</th>
                <th className="px-3 py-2">Tooling</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {STEPS.map((s) => (
                <tr key={s.n} className="align-top">
                  <td className="px-3 py-3 font-mono text-xs text-slate-500">{s.n}</td>
                  <td className="px-3 py-3 font-semibold text-slate-900">{s.step}</td>
                  <td className="px-3 py-3 text-slate-700">{s.what}</td>
                  <td className="px-3 py-3 text-slate-700">{s.tooling}</td>
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
            <li key={s.n} className="rounded-lg border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-slate-900">
                  {s.n}. {s.step}
                </span>
                <StatusTag status={s.status} />
              </div>
              <p className="mt-1 text-sm text-slate-700">{s.what}</p>
              <p className="mt-1 text-xs text-slate-500">{s.tooling}</p>
            </li>
          ))}
        </ul>

        <p className="mt-3 text-xs text-slate-500">
          Mock means a stand-in with demo values. Simulated means the readings are generated, not measured. The gate, the
          review pause, the receipts and the tracing are real.
        </p>
      </div>

      <Collapsible title="What is MCP?">
        <p>
          MCP (Model Context Protocol) is a standard way for the planner to call tools. Think of a USB standard for AI
          tools: the planner asks for a tool by name, and any tool that follows the standard plugs in. That lets me swap the
          mock optimizer for a real one without changing the planner.
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
            <thead className="text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="py-1 pr-3"></th>
                <th className="py-1 pr-3">This demo</th>
                <th className="py-1">Real lab</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {[
                ["LLM input", "Goal and run history", "Plus literature, lab schedule and past scientist notes"],
                ["LLM tools", "One: propose ratios", "Several: literature search, failure lookup, optimizer"],
                ["LLM output", "Element set and route", "Plus a rationale a scientist can read"],
                ["Risk model", "Hard-coded lookup", "A trained model"],
                ["Planner mode", "Mock, no LLM call", "The LLM runs every batch"],
                ["Workcell", "Simulated readings", "Robots, SEM and XRD instruments"],
              ].map(([k, a, b]) => (
                <tr key={k}>
                  <td className="py-2 pr-3 font-medium text-slate-900">{k}</td>
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
