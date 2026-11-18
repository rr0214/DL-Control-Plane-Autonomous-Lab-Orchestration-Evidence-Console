# SDL Control Plane: behavior spec

This file says what each agent and tool is allowed to do, who approves what, and which rules force a scientist to look. It is written for people. Where the code disagrees with this file, the code is the bug or this file is stale; fix whichever is wrong.

Status key: **Built** = real code today. **Mock** = stand-in with demo values. **Planned** = not built yet (the build plan step is in brackets). Planned items are here so the contract is agreed before code is written.

## 1. The loop and who does each step

The order of steps is fixed in code (a LangGraph graph with fixed edges). Agents act inside a step. They never choose which step runs next.

| # | Step | Type | Status |
|---|------|------|--------|
| 1 | Customer targets in | person | Built |
| 2 | Literature suggests directions | LLM | Planned [S2]. Today a plain lookup in a curated file |
| 3 | Planner proposes recipes | LLM | Partly built. Real Claude call when an API key is set, otherwise a mock plan |
| 4 | Optimizer picks exact ratios | ML | Mock (fixed table, not a trained model) |
| 5 | Safety check | code | Built (Policy Kernel) |
| 6 | Scientist reviews risky plans | person | Built. Risk signals feeding it are a mock lookup |
| 7 | Make the sample | code | Simulated. No real synthesis |
| 8 | Measure properties | code | Partly built. Simulated scan only; composition, hardness, oxidation planned [S3] |
| 9 | Measurement check | code | Partly built. Scan threshold rule only [S3] |
| 10 | Diagnosis agent | LLM | Planned [S4] |
| 11 | Release check | person | Planned [S5] |

The same list is served by `GET /api/loop` (source: `backend/app/steps.py`) and shown in the Architecture tab. Every trace span carries `step_type`, `step_n` and `is_mock` so a trace row says what kind of step it is.

## 2. What each agent can and cannot do

### Planner (step 3, LLM)
- **Can:** read the campaign goal, the customer targets and prior runs; choose an element set and a processing route; call the ratio optimizer tool.
- **Cannot:** write composition percentages itself (the optimizer sets them); skip or reorder steps; call any tool other than the optimizer; see or change policy rules; approve anything.
- **Output:** candidate recipes. Each is checked by code before it goes anywhere.
- **Without an API key:** a fixed mock plan, labeled `mock` in the UI and in the run note.

### Literature agent (step 2, LLM) [S2, planned]
- **Can:** read the curated reference list and suggest directions (element families, routes) with citations from that list.
- **Cannot:** cite anything outside the list; propose a specific recipe; change targets.
- **Without an API key:** the current lookup, labeled `mock`.

### Diagnosis agent (step 10, LLM) [S4, planned]
- **Can:** read the lineage for one sample (recipe, measurements, checks, similar prior runs) and propose exactly one action: `re-measure` or `hold`, with a reason, and say whether the likely cause is the instrument, the material or the model.
- **Cannot:** release a sample, change a recipe, change a policy, or run any action. It proposes; the action gate decides.
- **Action gate (code):** accepts only `re-measure` or `hold`; rejects anything else; caps re-measures per sample; every proposal and gate result goes to the actions log.

## 3. Who approves what

| Decision | Who | Notes |
|----------|-----|-------|
| Set customer targets | Customer (person) | Defaults in the demo are illustrative examples |
| Block a recipe (restricted element, repeat of a failed run) | Policy Kernel (code) | No role can override it |
| Approve, revise or reject a risky recipe before synthesis | Scientist (PI) | Operator may revise only |
| Edit policy | Policy Owner | Cannot approve samples |
| Export receipts, view evidence | Auditor | Read only |
| Approve a diagnosis action | Action gate (code) [S4] | |
| Release a result against customer targets | Scientist (PI) [S5] | Planned |

Roles come from the client `X-Role` header in this demo. That is **not** real authentication; a real deployment would take the role from a signed identity.

## 4. Tool contracts (Core Platform tools, FastMCP)

| Tool | Input | Output | Type | Status |
|------|-------|--------|------|--------|
| `propose_alloy_ratios` | elements, processing route, n | composition percentages summing to 100 | ML | Mock: fixed table |
| `check_negative_runs` | composition, processing route, campaign id | prior runs with the same composition and route, including failed ones | code | Built |
| `search_calphad_literature` | elements, topic, limit | references with DOI links from a curated list | code | Built (plain lookup) |

Every tool call is traced with its transport (`fastmcp` or `direct` fallback).

## 5. Rules that force scientist review or a block

| Rule | Where | Effect |
|------|-------|--------|
| `RESTRICTED_ELEMENT` (hafnium) | Policy Kernel | Blocked. Never reaches a scientist or a robot |
| `DUPLICATE_CONDITION` (same composition and route as a failed run) | Policy Kernel | Blocked |
| Predicted ductility margin below 0.80 | Pre-synthesis risk model (mock lookup) | Paused for scientist review before anything is made |
| SEM confidence below 0.8 | Scan classification (simulated) | Yellow: scientist review |
| Crack found, or XRD match below 0.5 | Scan classification (simulated) | Red |

The hafnium rule and the customer's "reduced hafnium" target are different things: the first is a hard block on the lab floor, the second is a property the customer asks for.

## 6. What is not claimed
- Shadow replay against historical data is not built and is not claimed anywhere.
- Property measurements, the measurement check, the diagnosis agent and the release check are planned, not built.
- All numeric risk, ductility and instrument values are demo data unless the UI says otherwise.
