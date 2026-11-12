"use client";

import { useState } from "react";

type Component = { id: string; name: string; plane: "core" | "pluggable"; detail: string; status: "built" | "planned" };

const COMPONENTS: Component[] = [
  {
    id: "rbac",
    name: "RBAC governance",
    plane: "core",
    status: "built",
    detail: "Roles decide who may approve, rescan, or kill a sample. Enforced on every review call (X-Role header).",
  },
  {
    id: "langgraph",
    name: "LangGraph orchestrator",
    plane: "core",
    status: "built",
    detail: "StateGraph with SQLite checkpointing. A Yellow sample pauses with interrupt() and resumes with Command(resume=...).",
  },
  {
    id: "mcp",
    name: "MCP tool gateway",
    plane: "core",
    status: "planned",
    detail: "Planned: the single, audited door for agents to call instruments and tools. Not in this build yet.",
  },
  {
    id: "policy",
    name: "Policy Kernel",
    plane: "core",
    status: "built",
    detail: "Plain code, no LLM, under 50 ms. Blocks restricted elements and repeats of prior (composition + processing) runs.",
  },
  {
    id: "optimizer",
    name: "Bayesian optimizer",
    plane: "pluggable",
    status: "built",
    detail: "Swappable ML component. Mock surrogate today; the only source of numeric stoichiometry.",
  },
  {
    id: "llm",
    name: "LLM planner",
    plane: "pluggable",
    status: "built",
    detail: "Claude tool-calling when ANTHROPIC_API_KEY is set. Picks element sets and routes; never writes ratios.",
  },
  {
    id: "workcell",
    name: "Robotics workcell",
    plane: "pluggable",
    status: "built",
    detail: "Simulated telemetry today (SEM CV confidence, XRD phase match, crack detection). Swap for instrument drivers.",
  },
];

export default function ArchitectureTab() {
  const [selected, setSelected] = useState<string>("policy");
  const active = COMPONENTS.find((c) => c.id === selected) ?? COMPONENTS[0];

  const core = COMPONENTS.filter((c) => c.plane === "core");
  const pluggable = COMPONENTS.filter((c) => c.plane === "pluggable");

  const renderBox = (c: Component) => (
    <button
      key={c.id}
      onClick={() => setSelected(c.id)}
      className={`w-full rounded-lg border p-3 text-left transition ${
        selected === c.id
          ? "border-slate-900 bg-white shadow-md"
          : "border-slate-200 bg-white/70 hover:border-slate-400"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-900">{c.name}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
            c.status === "built" ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"
          }`}
        >
          {c.status}
        </span>
      </div>
    </button>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <div className="grid gap-4 lg:col-span-8 md:grid-cols-2">
        <div className="rounded-xl bg-sky-50 p-4 ring-1 ring-sky-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-sky-900">Core Platform Harness</h2>
          <p className="mt-1 text-xs text-sky-800">Stable. Governance and safety live here, not in the model.</p>
          <div className="mt-3 space-y-2">{core.map(renderBox)}</div>
        </div>
        <div className="rounded-xl bg-violet-50 p-4 ring-1 ring-violet-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-violet-900">Pluggable ML and Robotics Workcell</h2>
          <p className="mt-1 text-xs text-violet-800">Swappable. Each part can be replaced without touching the harness.</p>
          <div className="mt-3 space-y-2">{pluggable.map(renderBox)}</div>
        </div>
      </div>

      <aside className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200 lg:col-span-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{active.name}</h2>
          <span className="text-xs text-slate-500">{active.plane === "core" ? "Core harness" : "Pluggable"}</span>
        </div>
        <p className="mt-3 text-sm text-slate-700">{active.detail}</p>
        <p className="mt-4 text-xs text-slate-500">
          Click any component to see what it does and whether it is built yet.
        </p>
      </aside>
    </div>
  );
}
