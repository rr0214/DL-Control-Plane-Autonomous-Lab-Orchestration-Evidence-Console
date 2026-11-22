# SDL Control Plane

A real working prototype of a console for a self-driving materials lab. The pipeline of services, the safety gates and
the Claude agents are real, and every run is traced. The optimizer, the prediction model and the lab measurements are
simulated stand-ins that a real model or instrument can replace. The screens use example data, and each item is tagged
LIVE (from the API) or EXAMPLE.

**AI reads and explains, math predicts, code enforces, people approve.**

## What it does

A scientist enters targets for a new alloy (strength, temperature, hafnium content). The system plans a batch of
recipes, blocks anything that breaks a rule, pauses for a scientist on risky recipes, simulates making and measuring
the samples, checks the readings, asks Claude to diagnose anything flagged, and lets a person release or withhold each
sample, with a receipt that records the role that signed off.

The console has four screens:

- **Review queue** (`/`): customer requests, internal experiments and recipes waiting for a scientist. Approving or
  rejecting a live recipe resumes its paused run.
- **Active experiments** (`/experiments`): planned, running, measuring, complete and stopped experiments.
- **Add experiment** (`/experiments/new`): enter targets, run a real plan through the API, review it, and release a
  sample. The run's evidence (references, tool calls, Claude calls with tokens and cost, spans) is shown with it.
- **Architecture** (`/architecture`): where AI fits, the graph nodes, the steps read live from the backend, and how
  traces work.

## How it is built

- **Backend:** FastAPI and a LangGraph `StateGraph` (`backend/app/graph.py`). Every step is checkpointed in SQLite, so
  a run paused for a scientist can wait as long as needed and resume where it stopped. Campaigns, plans, samples and
  releases are stored in SQLite (`db.py`).
- **Frontend:** Next.js (App Router), React and Tailwind. It calls the API in `frontend/lib/api.ts`.
- **Tools:** an MCP tool gateway (FastMCP) with three tools.
- **Tracing:** OpenTelemetry to Arize Phoenix.
- **Hosting:** `render.yaml` defines three Render services, `sdl-api-rr`, `sdl-console-rr` and `sdl-phoenix-rr`
  (see `DEPLOY.md`). When `SDL_ACCESS_PASSWORD` is set, every API route except `/health` needs that password, and the
  console asks for it first. `SDL_DAILY_RUN_LIMIT` caps plan runs per UTC day.

## The 7 graph nodes and the 10 console steps

The graph has 7 nodes, run in a fixed order. If the target check fails, the run stops there.

| Graph node | What it does |
| --- | --- |
| `target_check` | Plain code checks the targets against the lab limits and stops impossible ones. |
| `setup_agent` | Claude reads the references and past runs and sets the search space. |
| `optimizer` | Picks the ratios from a fixed table, through the `propose_alloy_ratios` MCP tool. |
| `prediction_model` | Scores each recipe with a fixed lookup. There is no trained model. |
| `policy_kernel` | The safety gate: blocks restricted elements and repeats of past runs. |
| `triage_and_hitl` | Pauses risky recipes for a scientist, then simulates making and measuring, then checks the readings. |
| `diagnose_flagged` | Claude proposes re-measure or hold for flagged samples; a code gate decides. |

The console shows 10 steps. Eight run on the graph nodes, and two run outside the graph:

| Console step | Where it runs |
| --- | --- |
| 1. Targets | `target_check` |
| 2. Setup agent | `setup_agent` |
| 3. Optimizer and prediction | `optimizer` and `prediction_model` |
| 4. Safety gate | `policy_kernel` |
| 5. Scientist review | `triage_and_hitl`: the graph pauses with `interrupt()` |
| 6. Make and measure | `triage_and_hitl`: `workcell.py` and `measure.py` (simulated) |
| 7. Measurement check | `triage_and_hitl`: `check.py` |
| 8. Diagnosis | `diagnose_flagged`: Claude proposes, `action_gate.py` decides |
| 9. Save and learn | Outside the graph: SQLite writes after each step; `history.py` feeds past outcomes into the next setup agent's prompt. No retraining. |
| 10. Release | Outside the graph: the API route `POST /api/samples/{id}/release`, with rules in `release.py`. A person decides. |

## Where Claude is used

Claude is used in exactly two places, both through the Anthropic API. The default model is `claude-sonnet-5-5`
(`ANTHROPIC_MODEL`, or `SDL_MODEL_SETUP` and `SDL_MODEL_DIAGNOSIS` for each agent).

- **Setup agent** (`setup_agent.py`): code first looks up the literature through the MCP tool, then Claude reads the
  references and the run history and returns the search space through a single answer tool. The answer's element list
  is an enum without the restricted element, so Claude cannot ask for hafnium.
- **Diagnosis agent** (`diagnosis.py`): for each flagged sample, Claude replies in JSON with an action (re-measure or
  hold), a cause and a reason. It only proposes; the action gate decides.

Both cache their fixed instructions, and every call is timed and priced (`llm_usage.py`). Scientist notes and past
comments reach Claude as quoted data, never as instructions.

**With no API key:** the app still runs end to end. The setup step becomes a plain lookup with no search space, so the
optimizer uses only its fixed rows. Diagnosis uses a rule-based stand-in. Each such run is marked `mock`, and after a mock run the
console's banner says Claude replies are mocked. The same fallback is used if a Claude call fails.

## The MCP tool gateway

`mcp_server.py` defines three tools on a FastMCP server. The graph calls them through a gateway over an in-memory MCP
session. If that session is unavailable, the gateway calls the same Python functions directly and records which path
it used (`SDL_MCP_MODE=direct` forces the direct path).

| Tool | Called by | What it does |
| --- | --- | --- |
| `propose_alloy_ratios` | the `optimizer` node | Returns ratios from the simulated optimizer's fixed table. |
| `check_negative_runs` | the `policy_kernel` node | Looks for an earlier run with the same composition and processing. |
| `search_calphad_literature` | the setup agent | Searches the 5 curated papers in `literature.json`. Search is local, not live. |

Because the optimizer sits behind a tool, a real optimizer can replace the mock without changing the setup agent, as
long as it keeps the tool's inputs and outputs.

## The safety gates and where a person decides

Code enforces the rules; prompts are only context.

- **Target check** (`target_check.py`): targets outside the lab limits stop the run before any AI call.
- **Safety gate** (`policy_kernel.py`, no AI): blocks any recipe with a restricted element (`RESTRICTED_ELEMENT`,
  hafnium) and any repeat of a past run's composition and processing (`DUPLICATE_CONDITION`). Every batch includes two
  fixed probes, a hafnium recipe and an exact repeat of a past run, so both rules are exercised on every run
  (`proposer.py`).
- **Scientist review** (`presynthesis.py`): a recipe whose predicted ductility margin is below 0.80, or that contains a
  restricted element, pauses the graph before anything is made. **A person approves or rejects it**; a rejected recipe
  is never made.
- **Action gate** (`action_gate.py`): fails closed. The only actions are re-measure and hold; anything malformed or not
  allowed becomes hold. A Red sample can only be held, and a sample can be re-measured at most twice.
- **Release** (`release.py`): **a person releases or withholds each sample.** A Red sample can never be released, and
  releasing with an exception needs a written reason of at least 10 characters. Each accepted decision is saved with a
  receipt.

## What is simulated

- **Optimizer:** a fixed table of ratios (`optimizer.py`).
- **Prediction model:** a fixed lookup with no trained model (`prediction_model.py`).
- **Making and measuring:** `workcell.py` and `measure.py` simulate synthesis and the readings. Measured values in the
  console are labeled simulated.
- **Example data on the screens:** the customer requests, internal experiments and example recipes in
  `frontend/lib/seed/` are made up and tagged EXAMPLE. Runs you start in Add experiment are real API runs and are
  tagged LIVE.

## Traces in Arize Phoenix

Every plan, review and release is traced with OpenTelemetry and sent to Arize Phoenix over OTLP/HTTP (`telemetry.py`).
A plan's trace has a span for each graph node, plus spans for the MCP tool calls, the Claude calls (with tokens, cost and
latency), the safety gate, the scientist review, the measurement check, the action gate and the release sign-off. Live
runs go to the Phoenix project `sdl-control-plane`. If Phoenix cannot be reached when the API starts, the app runs
without tracing.

The hosted Phoenix requires a login, and the API sends its traces with a Phoenix API key. **A read-only login is
available on request.** The local Phoenix started by `start.sh` is open. Traces include prompts and Claude's replies,
so only example data is sent there.

## Run it locally

```bash
./start.sh
```

Then open http://localhost:3000. The API docs are at http://localhost:8000/docs and Phoenix is at
http://localhost:6006. You need Python 3 (the backend is run on 3.12) and Node.js with npm (Next.js 15 needs Node.js
18.18 or newer). The first start installs the dependencies and takes a few minutes.

`start.sh` creates `.env` from `.env.example` if it is missing. Add your `ANTHROPIC_API_KEY` there for live Claude
calls; without it the app runs in mock mode (see above).

Tests: `cd backend && .venv/bin/python -m pytest -q`.

## Design decisions

### 1. One setup agent, not two AI steps
* **Chose:** one AI call per batch that reads the papers and past results and returns the search space.
* **Passed on:** a separate literature agent and setup agent.
* **Why:** it is one job (decide what is worth exploring), so one owner is easier to evaluate and explain.
* **Trade-off:** lower cost and latency, and the fixed instructions are cached. I gave up tuning the two roles
  separately.

### 2. The AI draws the box, math picks the recipe
* **Chose:** the AI sets which elements are allowed and a range for each. The optimizer picks the exact ratios.
* **Passed on:** letting the AI write full recipes.
* **Why:** AI is good at judgment about what to explore and unreliable with precise numbers. An optimizer is testable,
  and the AI can never invent a recipe.
* **Trade-off:** it needs a real optimizer. Today it is simulated.

### 3. Rules live in code, prompts are only context
* **Chose:** "no hafnium" and "never repeat a past run" are enforced by code: the answer format leaves hafnium out, and
  the safety gate blocks it.
* **Passed on:** relying on a line in the prompt.
* **Why:** a prompt is a request the AI can miss. Code is a guarantee, can be audited, and does not change when the
  model changes.
* **Trade-off:** changing a rule means changing code. In return the check is free and instant.

### 4. The AI recommends, a gate decides
* **Chose:** the diagnosis agent can only suggest re-measure or hold. A code gate checks the suggestion and falls back to
  hold if anything looks off.
* **Passed on:** letting the agent act on its own.
* **Why:** the worst case of a wrong answer is a wasted suggestion.
* **Trade-off:** strict. When the reply is not in a form the gate accepts, the sample is held and the AI call is wasted.

### 5. A scientist approves before anything is made
* **Chose:** risky recipes pause for a scientist before synthesis.
* **Passed on:** reviewing after the measurement.
* **Why:** making a sample costs real time and money and cannot be undone.
* **Trade-off:** latency. A paused run can wait hours or days, but the checkpoint keeps its place. The review threshold
  is a dial: lower means fewer interruptions and more missed risks.

### 6. Notes from people are data, never instructions
* **Chose:** scientist notes and past comments reach the AI as quoted data only.
* **Why:** otherwise anyone who can write a note could steer the system (prompt injection).
* **Trade-off:** a note can inform the agent but never command it. Hard limits sit in code, so even a fooled agent
  cannot break them.

### 7. Plain-code checks first, an AI judge later
* **Chose:** the first evaluators are rules written in code.
* **Why:** they cost nothing, run instantly and give the same answer every time.
* **Trade-off:** they only catch what I thought to write down.

## Evals

- `front_half_cases.py` builds 20 test cases: 5 with impossible targets, 5 that force a hafnium pick and 10 clean ones.
  `golden.json` holds their expected answers.
- `front_half_evals.py` scores two code checks on the traces: impossible targets are flagged and stop the run, and
  hafnium is blocked before anything is made.
- To prove the checks can fail, it plants 9 mistakes in copies of real traces. Each must come out Fail.
- Known issue: the diagnosis agent's reply is capped at 400 tokens (`diagnosis.py`). In a live test run the reply hit
  that cap and the JSON was cut off, so the action gate held the sample. Raising the cap is the likely fix.

## Repo layout

```
backend/app/
  api.py                 FastAPI routes the console calls
  orchestrator.py        Starts a run and resumes it after a scientist review
  graph.py               The LangGraph workflow (7 nodes)
  target_check.py        Lab limits; stops impossible targets
  targets.py             Customer targets for a campaign
  setup_agent.py         Claude sets the search space
  history.py             Past outcomes fed to the setup agent
  optimizer.py           Simulated optimizer (a fixed table)
  prediction_model.py    Simulated prediction model (a fixed lookup)
  proposer.py            Gathers the candidates for the safety gate
  policy_kernel.py       Safety gate (restricted elements, repeated runs)
  presynthesis.py        Decides which recipes a scientist must review
  workcell.py            Simulated lab readings
  measure.py             Simulated measurements
  check.py               Measurement check
  diagnosis.py           Diagnosis agent (Claude)
  action_gate.py         Action gate (holds when unclear)
  release.py             Release rules and receipt
  steps.py               The step table the Architecture page reads
  mcp_server.py          MCP tools and the gateway
  literature.json        The 5 curated papers
  llm_usage.py           Times and prices every Claude call
  telemetry.py           Phoenix tracing through OpenTelemetry
  db.py, config.py       SQLite storage and settings
  front_half_*.py        The 20 test cases, the runner and the evals
  run_evals.py           Earlier evals and the review threshold comparison
  seed_phoenix.py        Six curated example traces for Phoenix
backend/tests/           pytest suite
frontend/app/            Routes: / (Review queue), /experiments, /experiments/new, /architecture
frontend/components/
  app/                   Header, banner, theme switch, tags
  review/                Review queue
  experiments/           Active experiments
  addexp/                Add experiment and its evidence panel
  architecture/          Architecture page sections
frontend/lib/            API calls, stores, loop steps, example data (seed/)
render.yaml, DEPLOY.md   Render hosting
start.sh                 Starts Phoenix, the API and the console
```

## Next

* Raise the diagnosis token limit.
* Send the Goal typed in Add experiment to the planner (today the planner uses the campaign's fixed goal).
* Replace the simulated optimizer, prediction model and instruments with real ones.
