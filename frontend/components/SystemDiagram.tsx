// Engineering view of the running system: the three hosted services, the LangGraph pipeline inside the API, the MCP
// tools, the data stores and the outside services, with the protocol on every arrow. Each box says whether it is real
// code, simulated, a stand-in model or example data. Colors come from the design tokens, so both themes work.
// Kept in sync by hand with backend/app/graph.py (node order) and backend/app/steps.py (real vs simulated).

type Kind = "person" | "llm" | "ml" | "code" | "ext" | "store";
type Truth = "real" | "sim" | "example" | "fallback" | "mixed";

const KIND: Record<Kind, { box: string; title: string }> = {
  person: { box: "fill-ok-50 stroke-ok-400", title: "fill-ok-900" },
  llm: { box: "fill-ai-50 stroke-ai-400", title: "fill-ai-900" },
  ml: { box: "fill-warn-50 stroke-warn-400", title: "fill-warn-900" },
  code: { box: "fill-surface stroke-ink-400", title: "fill-ink-900" },
  ext: { box: "fill-info-50 stroke-info-400", title: "fill-info-900" },
  store: { box: "fill-cite-50 stroke-cite-400", title: "fill-cite-900" },
};

const TRUTH: Record<Truth, { label: string; tag: string; text: string }> = {
  real: { label: "REAL", tag: "fill-ok-100 stroke-ok-300", text: "fill-ok-800" },
  sim: { label: "SIMULATED", tag: "fill-danger-100 stroke-danger-300", text: "fill-danger-800" },
  example: { label: "EXAMPLE DATA", tag: "fill-warn-100 stroke-warn-300", text: "fill-warn-900" },
  fallback: { label: "REAL + MOCK FALLBACK", tag: "fill-info-100 stroke-info-300", text: "fill-info-900" },
  mixed: { label: "LIVE + EXAMPLE DATA", tag: "fill-ok-100 stroke-ok-300", text: "fill-ok-800" },
};

function Box({
  x, y, w, h, kind, truth, title, lines = [],
}: { x: number; y: number; w: number; h: number; kind: Kind; truth: Truth; title: string; lines?: string[] }) {
  const k = KIND[kind];
  const t = TRUTH[truth];
  const stand = truth === "sim" || truth === "example";
  const tagW = t.label.length * 5.6 + 10;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={6} className={k.box} strokeWidth={1.5} strokeDasharray={stand ? "5 3" : undefined} />
      {stand && <rect x={x} y={y} width={w} height={h} rx={6} fill="url(#sim-hatch)" />}
      <text x={x + 8} y={y + 17} className={`${k.title} font-mono text-[11.5px] font-semibold`}>{title}</text>
      {lines.map((l, i) => (
        <text key={i} x={x + 8} y={y + 32 + i * 13} className="fill-ink-700 text-[10px]">{l}</text>
      ))}
      <rect x={x + w - tagW - 4} y={y + h - 16} width={tagW} height={12} rx={3} className={t.tag} strokeWidth={0.75} />
      <text x={x + w - tagW / 2 - 4} y={y + h - 7} textAnchor="middle" className={`${t.text} text-[8px] font-semibold tracking-wide`}>{t.label}</text>
    </g>
  );
}

function Zone({ x, y, w, h, title, sub }: { x: number; y: number; w: number; h: number; title: string; sub: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} className="fill-ink-50 stroke-ink-300" strokeWidth={1} />
      <text x={x + 12} y={y + 20} className="fill-ink-900 text-[12.5px] font-semibold">{title}</text>
      <text x={x + 12} y={y + 34} className="fill-ink-500 text-[10px]">{sub}</text>
    </g>
  );
}

// Orthogonal arrow through the given points, with an optional label at a point.
function Wire({ pts, label, at, dashed = false }: { pts: [number, number][]; label?: string; at?: [number, number]; dashed?: boolean }) {
  return (
    <g>
      <polyline
        points={pts.map((p) => p.join(",")).join(" ")}
        fill="none"
        className="stroke-ink-500"
        strokeWidth={1.25}
        strokeDasharray={dashed ? "4 3" : undefined}
        markerEnd="url(#arrow)"
      />
      {label && at && (
        <text x={at[0]} y={at[1]} className="fill-ink-600 text-[9.5px]" textAnchor="middle" paintOrder="stroke" stroke="rgb(var(--surface))" strokeWidth={3}>
          {label}
        </text>
      )}
    </g>
  );
}

// A graph node that contains several parts: a labeled frame around them.
function NodeFrame({ x, w, id, note }: { x: number; w: number; id: string; note: string }) {
  return (
    <g>
      <rect x={x} y={R2} width={w} height={IR - R2 + NH + 8} rx={7} className="fill-ink-50 stroke-ink-500" strokeWidth={1.25} />
      <text x={x + 8} y={R2 + 14} className="fill-ink-900 font-mono text-[11px] font-semibold">
        {id}
        <tspan className="fill-ink-600 font-sans text-[9.5px] font-normal"> graph node: {note}</tspan>
      </text>
    </g>
  );
}

// Pipeline geometry: two rows of five nodes inside the orchestrator.
const COL = [312, 452, 592, 732, 872];
const NW = 128;
const NH = 72;
const R1 = 186;
const R2 = 292; // top of the two node frames in row 2
const IR = R2 + 20; // inner boxes inside those frames

export default function SystemDiagram() {
  return (
    <div className="overflow-x-auto">
      <svg viewBox="0 0 1300 730" className="min-w-[960px]" role="img" aria-labelledby="sysdiag-title sysdiag-desc">
        <title id="sysdiag-title">System architecture of the SDL Control Plane</title>
        <desc id="sysdiag-desc">
          A Next.js console calls a FastAPI service over HTTPS. Inside it, a LangGraph graph of seven nodes runs in a fixed
          order (scientist review, make and measure and the measurement check run inside one node), and calls three MCP tools, writes to two SQLite files, calls Claude, and sends traces to Arize Phoenix.
          Optimizer, prediction, synthesis and measurement are simulated.
        </desc>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="fill-ink-500" />
          </marker>
          <pattern id="sim-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" className="stroke-ink-300" strokeWidth={1.5} opacity={0.45} />
          </pattern>
        </defs>

        {/* ---- Browser ---- */}
        <Zone x={16} y={16} w={236} h={540} title="Browser: Next.js 15 console" sub="Render web service sdl-console-rr" />
        <Box x={30} y={66} w={208} h={66} kind="code" truth="mixed" title="Review queue" lines={["requests: seeded examples;", "Internal experiments:", "live + seeded"]} />
        <Box x={30} y={142} w={208} h={58} kind="code" truth="real" title="Add experiment" lines={["plan, review, results"]} />
        <Box x={30} y={210} w={208} h={58} kind="code" truth="mixed" title="Active experiments" lines={["live runs + seeded examples"]} />
        <Box x={30} y={278} w={208} h={58} kind="code" truth="real" title="Architecture" lines={["step table from /api/loop"]} />
        <Box x={30} y={436} w={208} h={92} kind="code" truth="real" title="Banner + header" lines={["banner: Claude live, or mocked", "if the newest run was mock;", "Phoenix traces link"]} />
        <Box x={30} y={346} w={208} h={80} kind="code" truth="real" title="PasswordGate + apiFetch" lines={["adds X-Access-Password to every", "call; review and release calls", "also send X-Role"]} />

        {/* ---- API service ---- */}
        <Zone x={286} y={16} w={734} h={700} title="API service: FastAPI + LangGraph (Python)" sub="Render web service sdl-api-rr, 1 GB persistent disk" />
        <Box x={300} y={52} w={706} h={60} kind="code" truth="real" title="HTTP edge (api.py)"
          lines={["CORS allow-list · shared access password on every route but /health · daily plan-run limit (429)", "role check from the X-Role header: enforced on the server, but not real sign-in"]} />

        <rect x={300} y={122} width={706} height={278} rx={8} className="fill-surface stroke-ink-300" strokeWidth={1} strokeDasharray="2 2" />
        <text x={312} y={140} className="fill-ink-900 text-[11.5px] font-semibold">CampaignOrchestrator: LangGraph StateGraph, 7 nodes, fixed edges</text>
        <text x={312} y={154} className="fill-ink-500 text-[10px]">Agents act inside a node and never choose the next one. A pause is saved and resumed from a checkpoint.</text>

        <Box x={COL[0]} y={R1} w={NW} h={NH} kind="code" truth="real" title="target_check" lines={["lab limits; stops", "impossible targets"]} />
        <Box x={COL[1]} y={R1} w={NW} h={NH} kind="llm" truth="fallback" title="setup_agent" lines={["Claude sets the", "search space"]} />
        <Box x={COL[2]} y={R1} w={NW} h={NH} kind="ml" truth="sim" title="optimizer" lines={["fixed table, not", "a trained optimizer"]} />
        <Box x={COL[3]} y={R1} w={NW} h={NH} kind="ml" truth="sim" title="prediction_model" lines={["fixed lookup, no", "trained model"]} />
        <Box x={COL[4]} y={R1} w={NW} h={NH} kind="code" truth="real" title="policy_kernel" lines={["safety gate: blocks Hf", "and failed repeats"]} />

        {/* Row 2: two graph nodes. Their inner parts are drawn inside them, because they are not separate nodes. */}
        <NodeFrame x={304} w={416} id="triage_and_hitl" note="pause for review, then make, measure and check" />
        <NodeFrame x={726} w={276} id="diagnose_flagged" note="propose, then gate" />
        <Box x={312} y={IR} w={NW} h={NH} kind="person" truth="real" title="scientist review" lines={["interrupt() pauses;", "risk signals are mock"]} />
        <Box x={450} y={IR} w={NW} h={NH} kind="code" truth="sim" title="make + measure" lines={["no real synthesis;", "scan and values faked"]} />
        <Box x={588} y={IR} w={NW} h={NH} kind="code" truth="real" title="check.py" lines={["measurement check", "on simulated data"]} />
        <Box x={734} y={IR} w={NW} h={NH} kind="llm" truth="fallback" title="diagnosis.py" lines={["Claude proposes", "re-measure or hold"]} />
        <Box x={870} y={IR} w={NW} h={NH} kind="code" truth="real" title="action_gate.py" lines={["only re-measure or", "hold; fails closed"]} />

        {/* pipeline wires */}
        {COL.slice(0, 4).map((c, i) => (
          <Wire key={`r1-${i}`} pts={[[c + NW, R1 + NH / 2], [COL[i + 1], R1 + NH / 2]]} />
        ))}
        <Wire pts={[[COL[4] + NW / 2, R1 + NH], [COL[4] + NW / 2, R1 + NH + 10], [COL[0] + NW / 2, R1 + NH + 10], [COL[0] + NW / 2, R2]]} />
        {[[440, 450], [578, 588], [716, 734], [862, 870]].map(([a, b]) => (
          <Wire key={`r2-${a}`} pts={[[a, IR + NH / 2], [b, IR + NH / 2]]} />
        ))}
        <Wire pts={[[300, R1 + NH / 2], [COL[0], R1 + NH / 2]]} />

        <Box x={COL[0]} y={414} w={268} h={52} kind="person" truth="real" title="release.py: release check" lines={["compares results with customer targets"]} />
        <Box x={COL[2]} y={414} w={268} h={52} kind="code" truth="real" title="history.py: save and learn" lines={["outcomes saved in SQLite feed the next plan"]} />
        <Box x={COL[4]} y={414} w={NW} h={52} kind="code" truth="real" title="telemetry.py" lines={["OpenTelemetry spans"]} />

        <rect x={300} y={482} width={706} height={128} rx={8} className="fill-surface stroke-ink-300" strokeWidth={1} strokeDasharray="2 2" />
        <text x={312} y={500} className="fill-ink-900 text-[11.5px] font-semibold">MCP tool gateway (mcp_server.py): FastMCP, in-memory session</text>
        <text x={312} y={514} className="fill-ink-500 text-[10px]">If the MCP session fails, the same functions run directly; every trace records which way.</text>
        <Box x={312} y={528} w={220} h={70} kind="ml" truth="sim" title="propose_alloy_ratios" lines={["ratios from a fixed table", "(the optimizer step)"]} />
        <Box x={544} y={528} w={220} h={70} kind="code" truth="real" title="check_negative_runs" lines={["SQL lookup of failed runs", "with the same recipe"]} />
        <Box x={776} y={528} w={218} h={70} kind="code" truth="real" title="search_calphad_literature" lines={["curated list of 5 papers,", "each with a DOI; local search"]} />
        <Wire dashed pts={[[586, 400], [586, 482]]} />
        <text x={594} y={476} className="fill-ink-600 text-[9.5px]">MCP calls from setup_agent, optimizer, policy_kernel</text>

        <Box x={300} y={628} w={706} h={72} kind="code" truth="real" title="Routes"
          lines={["POST /api/campaigns/plan · POST /api/samples/{id}/review · GET and POST /api/samples/{id}/release · POST /api/demo/reset", "GET /api/campaigns/{id} · /api/loop · /api/health · /api/usage/summary · /api/evals/summary · /health (open, no password)"]} />

        {/* ---- Data and outside services ---- */}
        <Zone x={1054} y={16} w={230} h={700} title="Data and outside services" sub="" />
        <Box x={1068} y={52} w={202} h={92} kind="ext" truth="fallback" title="Anthropic API: Claude" lines={["called by setup_agent and", "diagnose_flagged; no key or", "an error: mock, labeled mock"]} />
        <Box x={1068} y={178} w={202} h={124} kind="store" truth="real" title="SQLite: sdl.db" lines={["campaigns, runs, plans,", "samples, actions, releases,", "run_counts (daily limit)", "on the persistent disk"]} />
        <Box x={1068} y={322} w={202} h={78} kind="store" truth="real" title="SQLite: checkpoints" lines={["LangGraph SqliteSaver:", "a paused run survives a restart"]} />
        <Box x={1068} y={430} w={202} h={104} kind="ext" truth="real" title="Arize Phoenix" lines={["trace viewer; live runs go to", "project sdl-control-plane;", "sdl-phoenix-rr: login required", "(open locally); 1 GB disk"]} />

        {/* cross-zone wires */}
        <Wire pts={[[238, 92], [300, 92]]} label="HTTPS" at={[269, 86]} />
        <Wire pts={[[1006, 160], [1040, 160], [1040, 120], [1068, 120]]} label="HTTPS" at={[1030, 154]} />
        <Wire pts={[[1006, 240], [1068, 240]]} label="SQL" at={[1037, 234]} />
        <Wire pts={[[1006, 360], [1068, 360]]} label="every step" at={[1037, 354]} />
        <Wire pts={[[COL[4] + NW, 440], [1040, 440], [1040, 476], [1068, 476]]} label="OTLP/HTTP" at={[1037, 434]} />
      </svg>
    </div>
  );
}

export function SystemDiagramLegend() {
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-600">
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-ok-100 ring-1 ring-ok-400 align-middle" />person decides</span>
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-ai-100 ring-1 ring-ai-400 align-middle" />AI agent (Claude)</span>
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-warn-100 ring-1 ring-warn-400 align-middle" />numeric model</span>
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-surface ring-1 ring-ink-400 align-middle" />plain code</span>
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-cite-100 ring-1 ring-cite-400 align-middle" />data store</span>
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-info-100 ring-1 ring-info-400 align-middle" />outside service</span>
      <span><span className="mr-1 inline-block h-3 w-3 rounded-sm border border-dashed border-ink-500 align-middle" />dashed and hatched: simulated or example data, not real</span>
    </div>
  );
}
