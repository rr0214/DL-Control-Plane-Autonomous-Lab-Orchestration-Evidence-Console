# SDL Control Plane: Autonomous Lab Orchestration & Evidence Console

A full-stack prototype of a compound agentic system for an autonomous materials lab. An LLM planner proposes alloy batches, a deterministic Policy Kernel gates them before any sample is made, and a LangGraph workflow pauses for a scientist whenever sensor data is ambiguous. Every decision leaves an evidence receipt and an OpenTelemetry-shaped trace.

Built as a portfolio project to show product decisions: where the model is allowed to act, where code must decide, and where a human must sign off.

## Quick start

```bash
./start.sh
```

Then open http://localhost:3000. The API docs are at http://localhost:8000/docs.

The script creates `.env` from `.env.example`, installs the Python and Node dependencies, and starts both servers. Ctrl+C stops both.

Requirements: Python 3.11 or newer, Node.js 18 or newer.

## Two modes, one codebase

| Mode | When | What happens |
|---|---|---|
| Mock (default) | No `ANTHROPIC_API_KEY` in `.env` | A fixed, deterministic plan runs. Works offline and costs nothing. |
| Real LLM | `ANTHROPIC_API_KEY` is set | Claude chooses element sets and processing routes through tool-calling. If the call fails, the run falls back to the mock plan and says so in the notes. |

In both modes:

- **Ratios come only from `bayesian_optimizer`.** The model never writes stoichiometry.
- **Two boundary probes are always appended:** a candidate containing the restricted element Hf, and an exact repeat of Run-088 (Nb50-Ti20-Cr15-Al15, Arc-Melt). The Policy Kernel blocks both, so the gate is always visible.
- **One demo Yellow control is always appended:** the same composition as Run-088 on a new route (Additive/Anneal). The gate allows it, and its SEM scan is ambiguous, so the scientist's review card always appears. This is a demo device that guarantees the human-in-the-loop step is visible, not a model choice.

## Architecture

```
frontend (Next.js, Tailwind)            backend (FastAPI)
┌──────────────────────────┐            ┌─────────────────────────────────────────┐
│ Lab Control Console      │ ──HTTP──▶  │ /api/campaigns/CAMP-014   (state, RBAC)  │
│ System Architecture      │            │ /api/campaigns/plan       (run graph)    │
│ Evals & Golden Dataset   │            │ /api/samples/{id}/review  (resume)       │
└──────────────────────────┘            └──────────────┬──────────────────────────┘
                                                       │
                              LangGraph StateGraph (CampaignOrchestrator)
                              SqliteSaver checkpoints every step
                                                       │
  retrieve_context ─▶ propose_candidates ─▶ policy_kernel ─▶ triage_and_hitl
   (SQLite history)   (LLM tool-calling      (deterministic,   (Green auto-advances,
                       or mock + probes)      under 50 ms)      Red early-kill,
                                                                Yellow interrupt())
```

### Core platform vs pluggable parts

- **Core harness (stable):** RBAC, the LangGraph orchestrator, the Policy Kernel, and the audit trail. Governance lives here, not in the model.
- **Pluggable (swappable):** the Bayesian optimizer, the LLM planner, and the workcell telemetry feed. Each can be replaced without changing the harness.

## Human-in-the-loop

A Yellow sample pauses the graph with `interrupt()`. The checkpointer saves its state, so a scientist can review it hours or days later. Resuming with `Command(resume=...)` continues from that exact point.

Each review decision is checked against RBAC. For example, an Operator can rescan a sample but cannot approve it. Every decision is stored with a receipt hash and an optional one-line intuition note.

The Yellow trigger is sensor ambiguity (SEM CV confidence 0.71 in the demo), not composition novelty. That distinction tells the scientist the measurement is uncertain, not that the alloy is new.

## Policy Kernel rules

| Rule | Example | Result |
|---|---|---|
| `RESTRICTED_ELEMENT` | Any candidate containing Hf | Blocked before any sample is made |
| `DUPLICATE_CONDITION` | Nb50-Ti20-Cr15-Al15 + Arc-Melt (same as Run-088) | Blocked |
| Same composition, new route | Nb50-Ti20-Cr15-Al15 + Additive/Anneal | Allowed |

Composition matching ignores element order, and processing matching ignores case.

## Repository layout

```
backend/
  app/
    api.py              FastAPI routes and RBAC checks
    graph.py            LangGraph StateGraph nodes
    orchestrator.py     CampaignOrchestrator (plan, review)
    proposer.py         LLM tool-calling or mock plan, plus boundary probes
    policy_kernel.py    Deterministic gate
    optimizer.py        bayesian_optimizer tool (mock surrogate)
    workcell.py         Simulated telemetry and Green/Yellow/Red classifier
    mcp_server.py       FastMCP tool contract and in-memory ToolGateway
    literature.json     Curated CALPHAD and refractory-alloy references (DOIs checked)
    seed_camp014.py     RBAC, evidence receipts, span trees
    db.py               SQLite schema, seed data, lineage tables
  tests/                pytest suite (policy, graph pause/resume, API, proposer)
frontend/
  app/                  Next.js App Router pages
  components/           ConsoleTab, ArchitectureTab, EvalsTab
  lib/api.ts            Typed API client
start.sh                Installs and runs everything
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

Current suite: 27 tests covering policy rules, the pause and resume cycle, RBAC enforcement, reset behavior, MCP tool contracts, the FastMCP and direct transports, and probe behavior in both modes.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Enables real LLM planning when set |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used for tool-calling |
| `SDL_DB_PATH` | `backend/data/sdl.db` | Campaign and lineage database |
| `SDL_CHECKPOINT_PATH` | `backend/data/checkpoints.sqlite` | LangGraph checkpoints |

## Known limits

- **Simulated data.** Telemetry, span timings, and eval numbers are demo values. The Evals tab labels its numbers as placeholders.
- **Optimizer is a stand-in.** `bayesian_optimizer` returns a fixed table. A real version would fit a surrogate model (such as a Gaussian process) on measured runs.
- **OpenAI is not wired.** Only Anthropic is supported in real mode.
- **Rescan does not re-queue a sample.** It is recorded as a decision, and the workflow moves on.
- **Literature is a curated list.** Six papers were checked against their text. Search is local, not live.
- **Reset Demo clears only CAMP-014.** Plans, samples, and checkpoints for that campaign are removed. Seed runs stay.

## MCP tool contract

Three tools, defined once in `backend/app/mcp_server.py` with FastMCP:

| Tool | What it does |
|---|---|
| `propose_alloy_ratios` | Returns numeric compositions (percent, summing to 100) from the optimizer for an element set and route |
| `check_negative_runs` | Looks up prior runs with the same composition and route, including failed ones (for example, Run-088) |
| `search_calphad_literature` | Returns phase-stability and CALPHAD references with DOIs |

The graph calls these through an in-memory MCP session, so the protocol is real but no subprocess is needed. If that session fails, the same functions run directly, and the trace records which transport was used. Set `SDL_MCP_MODE=direct` to skip FastMCP.

## Design notes

- Why deterministic code for the gate: a rule like "never use Hf" should not depend on a model's judgment. Code is auditable and fast, and it does not change when the model changes.
- Why the model only picks routes: the model is good at choosing what to explore. A numerical optimizer is better at choosing how much of each element to use, and it can be tested.
- Why interrupts, not polling: a paused run costs nothing while it waits, and its state survives restarts.
