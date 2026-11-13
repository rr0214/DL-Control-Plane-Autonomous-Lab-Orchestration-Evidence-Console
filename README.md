# SDL Control Plane: Autonomous Lab Orchestration & Evidence Console

A full-stack prototype of a compound agentic system for an autonomous materials lab. An LLM planner proposes alloy batches, a deterministic Policy Kernel gates them before any sample is made, and a LangGraph workflow pauses for a scientist whenever sensor data is ambiguous. Every decision leaves an evidence receipt and an OpenTelemetry-shaped trace.

Built as a portfolio project to show product decisions: where the model is allowed to act, where code must decide, and where a human must sign off.

## Quick start

```bash
./start.sh
```

Then open http://localhost:3000. The API docs are at http://localhost:8000/docs. Arize Phoenix (traces and evals) is at http://localhost:6006.

The script creates `.env` from `.env.example`, installs the Python and Node dependencies (it uses `uv` when installed, which is much faster than `pip`), starts Phoenix, seeds it, then starts the API and the web app. Ctrl+C stops everything. The first start takes a few minutes because Phoenix is a large install.

Requirements: Python 3.11 or newer, Node.js 18 or newer.

## Two modes, one codebase

| Mode | When | What happens |
|---|---|---|
| Mock (default) | No `ANTHROPIC_API_KEY` in `.env` | A fixed, deterministic plan runs. Works offline and costs nothing. |
| Real LLM | `ANTHROPIC_API_KEY` is set | Claude chooses element sets and processing routes through tool-calling. If the call fails, the run falls back to the mock plan and says so in the notes. |

In both modes:

- **Ratios come only from `bayesian_optimizer`.** The model never writes stoichiometry.
- **Two boundary probes are always appended:** a candidate containing the restricted element Hf, and an exact repeat of Run-088 (Nb50-Ti20-Cr15-Al15, Arc-Melt). The Policy Kernel blocks both, so the gate is always visible.
- **One demo Yellow control is always appended:** the same composition as Run-088 on a new route (Additive/Anneal). The gate allows it, and its mock pre-synthesis risk signals are borderline, so the scientist's review card always appears before anything is made. This is a demo device that guarantees the human-in-the-loop step is visible, not a model choice.

## Architecture

```
frontend (Next.js, Tailwind)            backend (FastAPI)
┌──────────────────────────┐            ┌─────────────────────────────────────────┐
│ Lab Control Console      │ ──HTTP──▶  │ /api/campaigns/CAMP-014   (state, RBAC)  │
│ System Architecture      │            │ /api/campaigns/plan       (run graph)    │
│ Evals (Error Analysis)   │            │ /api/samples/{id}/review  (resume)       │
└──────────────────────────┘            └──────────────┬──────────────────────────┘
                                                       │
                              LangGraph StateGraph (CampaignOrchestrator)
                              SqliteSaver checkpoints every step
                                                       │
  retrieve_context ─▶ propose_candidates ─▶ policy_kernel ─▶ triage_and_hitl
   (SQLite history)   (LLM tool-calling      (deterministic,   (risky recipe: interrupt() BEFORE
                       or mock + probes)      under 50 ms)      synthesis. Then scan triage for
                                                                what was made: Green advances,
                                                                Red early-kills.)
```

### Core platform vs pluggable parts

- **Core harness (stable):** RBAC, the LangGraph orchestrator, the Policy Kernel, and the audit trail. Governance lives here, not in the model.
- **Pluggable (swappable):** the Bayesian optimizer, the LLM planner, and the workcell telemetry feed. Each can be replaced without changing the harness.

## Human-in-the-loop

The review happens **before any sample is made**. After the Policy Kernel allows a recipe, mock pre-synthesis risk signals are computed (predicted ductility margin vs. Run-071, furnace blast radius, phase stability, restricted elements). If the risk is high (ductility margin under 0.80), the graph pauses with `interrupt()` and the scientist approves, revises, or rejects the recipe. The checkpointer saves its state, so the review can happen hours or days later. Resuming with `Command(resume=...)` continues from that exact point.

- **Approve:** the recipe is synthesized (simulated) and scanned. Scan triage runs on what was made: Green advances, Red early-kills, and an ambiguous scan is flagged for follow-up without pausing again.
- **Revise or Reject:** the recipe is held. No sample is made and no scan exists. It is recorded as `Held`.

Each review decision is checked against RBAC. For example, an Operator can revise a recipe but cannot approve or reject it. Every decision is stored with a receipt hash and an optional one-line intuition note.

The risk signals are a **mock lookup** with fixed demo values, labeled as such in the UI. Only the restricted-element check is real. A production version would use a trained model.

## Policy Kernel rules

| Rule | Example | Result |
|---|---|---|
| `RESTRICTED_ELEMENT` | Any candidate containing Hf | Blocked before any sample is made |
| `DUPLICATE_CONDITION` | Nb50-Ti20-Cr15-Al15 + Arc-Melt (same as Run-088) | Blocked |
| Same composition, new route | Nb50-Ti20-Cr15-Al15 + Additive/Anneal | Allowed |

Composition matching ignores element order, and processing matching ignores case.

## Observability: Arize Phoenix

Every run is traced with OpenTelemetry into Phoenix at http://localhost:6006. Tracing never blocks the app: spans export in the background, and if Phoenix is not running (or `SDL_TRACING=off`) the app runs normally without it.

| Phoenix project | What is in it |
|---|---|
| `sdl-control-plane` | **Live** traces from the UI: `campaign.plan`, one span per graph node, one `mcp.<tool>` span per tool call, `policy.check`, `sample.triage`, `scientist.review` |
| `sdl-control-plane-seed` | **Curated, illustrative** examples for error analysis. Not production data. |

Span attributes: `campaign_id`, `mcp_mode`, `policy_status` (Allowed or Blocked), `cv_confidence`, and `scientist_override` (true when the scientist did anything other than approve the recipe), plus `predicted_ductility_margin`, `furnace_blast_radius` and `review_required` on the `presynthesis.review` span. A pause is recorded as a pause, not an error. Because the graph resumes by re-running the paused node, that node appears twice in a reviewed run: once when it pauses and once when it resumes.

### Error-analysis workflow (Hamel Husain style)

`app/seed_phoenix.py` runs once Phoenix is up (safe to re-run; it exits if the dataset exists). It writes six curated traces with human annotations from annotator `seed-script`:

| Trace | Outcome | First upstream failure |
|---|---|---|
| Clean pass (new route for a known-good composition) | Pass | none |
| Clean pass (novel composition) | Pass | none |
| Hf (restricted element) proposed | Pass | `propose_candidates` (caught by the Policy Kernel) |
| Repeat of Run-088 (Arc-Melt) | Pass | `propose_candidates` (caught by the Policy Kernel) |
| False-positive Yellow on a clean alloy (`cv_confidence` 0.94) | Fail | `triage_and_hitl` |
| Blurry SEM scan auto-advanced (`cv_confidence` 0.86) | Fail | `triage_and_hitl` |

Each trace gets two annotations: `outcome` (Pass or Fail) and `first_upstream_failure` (the node where it first went wrong, with a one-line note). The labeled cases are promoted into the Phoenix dataset `sdl-golden-eval-v1`, where each row pairs a candidate with the status the system should produce.

The two Fail traces describe failure modes of an earlier build, when a scientist reviewed samples after the scan. The current scan rule is `cv_confidence < 0.8`, so today's code would not flag 0.94, and the blurry 0.86 scan is a gap in that rule. In the current flow the human review happens before synthesis. They are scenarios chosen to show the workflow, not a record of past runs.

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
    presynthesis.py     Mock pre-synthesis risk signals (deterministic)
    run_evals.py        Phoenix experiment: golden dataset v2, code evaluators, threshold comparison
    workcell.py         Simulated scan telemetry and Green/Yellow/Red classifier
    mcp_server.py       FastMCP tool contract and in-memory ToolGateway
    literature.json     Curated CALPHAD and refractory-alloy references (DOIs checked)
    telemetry.py        Phoenix tracing setup and span helper (degrades gracefully)
    seed_phoenix.py     Seeds curated traces, annotations, and the golden dataset
    seed_camp014.py     RBAC, evidence receipts, span trees
    db.py               SQLite schema, seed data, lineage tables
  tests/                pytest suite (policy, graph pause/resume, API, proposer, MCP, telemetry)
  pyproject.toml        Dependencies (requirements.txt mirrors it)
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

Current suite: 87 tests covering policy rules, the pre-synthesis risk signals, the pause and resume cycle, RBAC enforcement, reset behavior, MCP tool contracts, the FastMCP and direct transports, probe behavior in both modes, and tracing (off under test, safe when Phoenix is down, seed fixture shape). Tracing is forced off in tests, so no Phoenix is needed.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Enables real LLM planning when set |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used for tool-calling |
| `SDL_DB_PATH` | `backend/data/sdl.db` | Campaign and lineage database |
| `SDL_CHECKPOINT_PATH` | `backend/data/checkpoints.sqlite` | LangGraph checkpoints |
| `SDL_TRACING` | `on` | Set to `off` to disable Phoenix tracing |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006` | Where traces are sent |
| `SDL_PHOENIX_PROJECT` | `sdl-control-plane` | Phoenix project for live runs |

## Evals in Phoenix (Hamel Husain's error-analysis method)

Evaluation targets the **system**, not just the model. Plain-code checks come first; an LLM judge is reserved for subjective failures and is not built yet.

| Step | Where it lives |
|---|---|
| 1. Collect real traces | Live runs go to `sdl-control-plane`; curated examples to `sdl-control-plane-seed` |
| 2. Open coding (Pass/Fail plus first upstream failure) | `outcome` and `first_upstream_failure` annotations on the seed traces |
| 3. Axial coding (failure modes) | `failure_mode` in the metadata of dataset `sdl-golden-eval-v2` |
| 4. Targeted evaluators | `gate_correct` and `review_correct`, both plain code, run as a Phoenix experiment |
| 5. Promote overrides | `python -m app.promote_overrides` sends scientist overrides to `sdl-needs-expert-label` |

Failure modes: unsafe recipe passes the gate, a known failure is repeated, a risky recipe skips review, a safe recipe is over-escalated.

```
python -m app.run_evals --compare     # runs the experiment at review threshold 0.80 and 0.95
python -m app.run_evals --local       # score and print only, no Phoenix
```

Open Phoenix, then Datasets, `sdl-golden-eval-v2`, Experiments, and compare the two runs. At 0.80 one row fails (`missed-risk`: the mock risk model has no entry for that recipe). At 0.95 that row is caught, but three safe recipes are now sent to a scientist, so the overall score drops. That is the review-threshold tradeoff, made visible.

**Honest limits:** the expected labels are illustrative, written by the builder and not by a materials scientist. Seven rows demonstrate the workflow, not statistical confidence. The task runs the real Policy Kernel and pre-synthesis code on recorded inputs; it does not re-run the planner. `sdl-golden-eval-v1` is the earlier set, kept for reference.

### From scientist notes to new checks

When a scientist rejects a recipe, the one-line reason they type is saved on the `scientist.review` trace (`review_note`) and carried into the dataset `sdl-needs-expert-label`, with a first-pass `theme` tag. Run `python -m app.promote_overrides` to pull new overrides and print the notes grouped by theme. The same run also writes each note onto the matching `campaign.plan` span as a Phoenix annotation named `scientist_feedback` (label is the theme), so the note sits next to the gate and risk evidence needed to find the root cause. Re-running updates the annotation instead of duplicating it, and `--dry-run` writes nothing.

Example: three rejects with notes about furnace blast radius show a real gap. Blast radius is displayed on the review card but does not trigger the review today (only the predicted ductility margin does). That is the kind of finding that becomes a new rule and a new evaluator.

Themes use keyword matching, not an LLM, so they are a rough first pass. A person still reads the notes and owns the categories. Free text in traces is a privacy decision: in an ITAR setting you would add redaction before sending notes to a tracing tool.

## Known limits

- **Simulated data.** Telemetry and the in-app span inspector timings are demo values. The Evals tab results are computed live from the golden dataset, whose labels are illustrative. The Phoenix seed traces are curated examples, labeled as illustrative. Live Phoenix traces are real spans from real runs of this code.
- **Optimizer is a stand-in.** `bayesian_optimizer` returns a fixed table. A real version would fit a surrogate model (such as a Gaussian process) on measured runs.
- **OpenAI is not wired.** Only Anthropic is supported in real mode.
- **Revise does not re-queue a recipe.** It is recorded as a decision and the recipe is held. Nothing is re-proposed automatically.
- **Literature is a curated list.** Six papers were checked against their text. Search is local, not live.
- **Reset Demo clears only CAMP-014.** Plans, samples, and checkpoints for that campaign are removed. Seed runs stay.

## MCP tool contract

Three tools, defined once in `backend/app/mcp_server.py` with FastMCP:

| Tool | What it does |
|---|---|
| `propose_alloy_ratios` | Returns numeric compositions (percent, summing to 100) from the optimizer for an element set and route |
| `check_negative_runs` | Looks up prior runs with the same composition and route, including failed ones (for example, Run-088) |
| `search_calphad_literature` | Returns phase-stability and CALPHAD references with DOIs |

The graph calls these through an in-memory MCP session, so the protocol is real but no subprocess is needed. The code supports both `mcp` 1.x (`FastMCP`) and 2.x (`MCPServer`), because Phoenix pulls in 2.x. If that session fails, the same functions run directly, and the trace records which transport was used. Set `SDL_MCP_MODE=direct` to skip FastMCP.

## Design notes

- Why deterministic code for the gate: a rule like "never use Hf" should not depend on a model's judgment. Code is auditable and fast, and it does not change when the model changes.
- Why the model only picks routes: the model is good at choosing what to explore. A numerical optimizer is better at choosing how much of each element to use, and it can be tested.
- Why interrupts, not polling: a paused run costs nothing while it waits, and its state survives restarts.
