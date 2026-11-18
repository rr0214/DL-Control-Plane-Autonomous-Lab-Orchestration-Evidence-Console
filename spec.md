# SDL Control Plane: behavior spec

This file says what each agent and tool is allowed to do, who approves what, and which rules force a scientist to look. It is written for people. Where the code disagrees with this file, the code is the bug or this file is stale; fix whichever is wrong.

Status key: **Built** = real code today. **Mock** = stand-in with demo values. **Planned** = not built yet (the build plan step is in brackets). Planned items are here so the contract is agreed before code is written.

## 1. The loop and who does each step

The order of steps is fixed in code (a LangGraph graph with fixed edges). Agents act inside a step. They never choose which step runs next.

| # | Step | Type | Status |
|---|------|------|--------|
| 1 | Customer targets in | person | Built |
| 2 | Literature suggests directions | LLM | Partly built. Real Claude call when an API key is set; otherwise a plain lookup with no directions |
| 3 | Planner proposes recipes | LLM | Partly built. Real Claude call when an API key is set, otherwise a mock plan |
| 4 | Optimizer picks exact ratios | ML | Mock (fixed table, not a trained model) |
| 5 | Safety check | code | Built (Policy Kernel) |
| 6 | Scientist reviews risky plans | person | Built. Risk signals feeding it are a mock lookup |
| 7 | Make the sample | code | Simulated. No real synthesis |
| 8 | Measure properties | code | Simulated. Composition, hardness and oxidation (mock formulas, `measure.py`) plus the earlier scan fields |
| 9 | Measurement check | code | Built (`check.py`). Real rules, simulated inputs |
| 10 | Diagnosis agent | LLM | Partly built. Real Claude call when an API key is set, otherwise a rule-based stand-in; code gate is real; actions are logged, not executed |
| 11 | Release check | person | Built. Strength is an estimate from simulated data; temperature is not assessed |

The same list is served by `GET /api/loop` (source: `backend/app/steps.py`) and shown in the Architecture tab. Every trace span carries `step_type`, `step_n` and `is_mock` so a trace row says what kind of step it is.

## 2. What each agent can and cannot do

### Planner (step 3, LLM)
- **Can:** read the campaign goal, the customer targets and prior runs; choose an element set and a processing route; call the ratio optimizer tool.
- **Cannot:** write composition percentages itself (the optimizer sets them); skip or reorder steps; call any tool other than the optimizer; see or change policy rules; approve anything.
- **Output:** candidate recipes. Each is checked by code before it goes anywhere.
- **Its pick is kept.** If the planner proposes something that repeats a failed run, the Policy Kernel blocks it and the trace shows it; the pick is never silently replaced.
- **Without an API key, or if the call fails:** a fixed mock plan, labeled `mock` in the UI and in the run note. When Claude made the proposal the run note says so, with the model name.

### Literature agent (step 2, LLM)
- **Can:** read the references that code retrieved from the curated list and suggest up to 3 directions (element additions, routes) with citations.
- **Cannot:** cite anything that was not retrieved (code drops any direction without a valid citation); propose a specific recipe or percentages; change targets; call tools (code does the retrieval first, which is also cheaper and faster than a tool loop).
- **Without an API key, or if the call fails:** a plain lookup, no directions, labeled `mock` in the UI and the run note.

### Diagnosis agent (step 10, LLM)
- **When it runs:** only for a sample that was actually made and came out Yellow or Red. Green, held and rejected samples are not diagnosed. One call per flagged sample.
- **Can:** read that sample's lineage (recipe, scan, measurements, failed checks, similar prior runs with their values, pre-synthesis risk signals, the scientist's decision and note) and propose exactly one action: `re-measure` or `hold`, with a reason, and say whether the likely cause is the `instrument`, the `material` or the `model`.
- **Cannot:** release a sample, change a recipe, change a policy, or run anything. It proposes; the action gate decides. Scientist notes in its input are quoted data, never instructions.
- **Without an API key, or if the call fails:** a fixed rule-based stand-in proposes instead, labeled `mock`.
- **Prompt version:** `diagnosis-v1`.

## 3. Who approves what

| Decision | Who | Notes |
|----------|-----|-------|
| Set customer targets | Customer (person) | Defaults in the demo are illustrative examples |
| Block a recipe (restricted element, repeat of a failed run) | Policy Kernel (code) | No role can override it |
| Approve, revise or reject a risky recipe before synthesis | Scientist (PI) | Operator may revise only |
| Edit policy | Policy Owner | Cannot approve samples |
| Export receipts, view evidence | Auditor | Read only |
| Approve a diagnosis action | Action gate (code) | Only `re-measure` or `hold` exist. Release is not an action |
| Release or withhold a result against customer targets | Scientist (PI) only (`release` permission) | A Red sample cannot be released. An exception needs a written reason |

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
| Impossible reading (composition not summing to 98 to 102%, hardness outside 50 to 1500 HV, negative oxidation) | Measurement check | Red |
| Restricted element measured above 0.1 at% | Measurement check | Red |
| Measured composition more than 1.0 at% from the recipe, or an unexpected element above 0.5 at% | Measurement check | Yellow |
| Hardness more than 30% or oxidation more than 50% away from similar compositions | Measurement check | Yellow |
| Red sample at release | Release check (`RED_NO_RELEASE`) | Cannot be released, only withheld |
| Release with an exception: a missed target, a Yellow status, or an open diagnosis hold | Release check (`NOTE_REQUIRED`) | Needs a written reason of at least 10 characters |

The hafnium rule and the customer's "reduced hafnium" target are different things: the first is a hard block on the lab floor, the second is a property the customer asks for.

## 6. Measurement check (step 9)
Plain code in `backend/app/check.py`. Inputs today are simulated (`measure.py`, labeled mock everywhere); the rules are real.
- **Fixed rules:** readings must be physically sensible, and no restricted element may appear in the sample.
- **Recipe vs measured:** every element within 1.0 at% of the recipe.
- **Anomaly vs similar:** compare hardness and oxidation to prior samples whose composition is close (summed difference under 20 at%): the seed runs and every earlier sample that was made. With no similar sample the check says "not assessed" and does not flag.
- **Effect:** the check can only make a sample's status worse (Yellow or Red), never better. It does not release anything. Acting on a flag is the diagnosis agent's job, behind the action gate [S4].
- The thresholds are demo defaults set by the builder, not validated against a real lab.

## 7. Action gate and actions log (step 10)
Plain code in `backend/app/action_gate.py`. The gate fails closed: anything it does not allow becomes `hold`.

| Rule | Condition | Result |
|------|-----------|--------|
| `INVALID_PROPOSAL` | Action is not `re-measure` or `hold`, cause is not instrument, material or model, or the reason is empty | Held |
| `RED_HOLD_ONLY` | Proposes re-measure for a Red sample or one with a restricted element | Held |
| `REMEASURE_CAP` | Already re-measured twice in the same plan | Held |
| none | Otherwise | The proposal is used |

- **Logged, not executed.** Every proposal and gate result goes to the actions log (the `actions` table, shown in the console). `executed` stays false: no real workcell is wired in.
- **The cap is counted per plan** (sample ids repeat across plans in this demo). Because nothing re-measures yet, the cap cannot trigger in normal use; it is unit tested and will matter once a re-measure loop exists.
- A hold does not change the sample's status or release anything. Release is a scientist's decision at the release check [S5].

## 8. Release check (step 11)
A person decides; code (`backend/app/release.py`) does the comparison and enforces the rules. It applies to a sample that was actually made.

| Customer target | Compared with | Basis |
|-----------------|---------------|-------|
| High temperature performance (minimum service temperature) | Nothing: no instrument measures it | **Not assessed until measured.** Shown as neither pass nor fail, and recorded as not assessed in the receipt |
| Strength (minimum yield) | Yield strength derived from hardness (about HV x 9.807 / 3) | **Estimate**, a common rule of thumb |
| Reduced hafnium (maximum Hf) | Measured Hf from the simulated composition reading | Direct comparison on simulated data |

- The targets used are the ones the plan was run with.
- **Release** is allowed only for the Scientist (PI) role. A **Red** sample cannot be released at all. **Withhold** is always allowed and needs no reason.
- **Exceptions** (a missed target, a Yellow status, an open diagnosis hold; a target that is not assessed is shown and recorded but is not an exception) make a written reason mandatory for a release, and the exceptions are recorded in the receipt.
- One decision per sample per plan. Each decision saves a SHA-256 receipt (the same idea as the review receipts) that covers the targets, the comparison, the exceptions, the note and the role.
- The role comes from a client header in this demo, so the sign-off is **not** real authentication.
- The release decision and note also go back into what the planner reads next time.

## 9. What the planner reads about earlier work
Before each plan, code builds the run history the planner sees: the two seed runs, then the 10 most recent decided samples, oldest first. Samples still waiting for review are left out.
- **Each line has:** composition and route, outcome (a held sample is "Held (not made)"), who decided (scientist or system) and the decision, the measurement check flags, and the scientist's note (the "why").
- **Notes are untrusted text.** They are cleaned (control characters, quotes), cut to 200 characters, and shown to the model as quoted data. The planner prompt (`planner-v3`) says a note is information about a run, never an instruction.
- **Not wired to the Policy Kernel.** A scientist's reject informs the planner only. The kernel's repeat-run block still reads the run table, which only a code change or a Policy Owner edit can alter.
- A reset clears the samples, and with them this history.

## 10. Cost, latency and versions
Every real LLM call is recorded: input and output tokens, model, cost, latency, prompt version and git commit. They appear on the trace span (`llm.planner`, `llm.literature`), in the plan result, and in the Evals tab ("Cost and latency per plan"). Mock plans make no calls and show zero.
- Model per agent: `SDL_MODEL_PLANNER`, `SDL_MODEL_LITERATURE`, `SDL_MODEL_DIAGNOSIS`, else `ANTHROPIC_MODEL`, else `claude-sonnet-5-5`.
- Prices are a hand-set table in `backend/app/llm_usage.py`. **Verify against current pricing** before quoting any cost. A model with no price shows cost "n/a", never a guess.
- Prompt versions: `planner-v3`, `literature-v1`, `diagnosis-v1`. Change the string when the prompt changes.

## 11. What is not claimed
- Shadow replay against historical data is not built and is not claimed anywhere.
- Measurements are simulated; strength at release is an estimate from them and temperature is not assessed. Diagnosis actions are logged, not executed. Sign-off roles are not real authentication.
- All numeric risk, ductility and instrument values are demo data unless the UI says otherwise.
