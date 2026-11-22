# Before merging (radical-ui or scientist-app-v2 into deploy)

Work through this list in order. Merge only after the owner approves, as one merge, with the exact steps written down
first.

## Temporary items to remove

1. **The theme query switch: removed.** `ThemePreview.tsx`, its import and its line in `frontend/app/layout.tsx` are
   gone, so `?theme=` in the URL does nothing. The header switch stays: the default theme is light (`DEFAULT_THEME` in
   `layout.tsx`), a first visit opens in light, and the switch to dark is remembered in the browser. The small script
   in `layout.tsx` applies the saved choice before the first paint, which is why `suppressHydrationWarning` stays on
   `<html>`.
2. **Screens index and theme preview page.** None were added on this branch. If one is added later, list it here.
3. **Anything else added only for testing.** Nothing in the repo: the screenshot and walkthrough tooling lives outside
   it. The `data-row` and `data-id` attributes on list rows and detail panels are used by that tooling; they are
   harmless and can stay.

## Decisions still open (flagged, not changed)

4. **Phoenix has no password.** Anyone with the Phoenix URL can read traces, including prompts and replies.
5. **Real Radical logo and brand assets.** The header uses a text wordmark ("Radical"); no logo is drawn or copied.
   The history lines name R. Riggs as an example scientist (example data, not a real account).
6. **Lab check rules**, including the 5% near-limit margin (`frontend/lib/labCheck.ts`, `LAB_LIMITS`).
7. **The prototype banner** is on (`SHOW_PROTOTYPE_BANNER` in `frontend/lib/settings.ts`). Decide whether it stays on
   for the hosted demo.
8. **ESLint.** The frontend has no ESLint installed or configured, so `next build` only type-checks. Either add
   `eslint` and `eslint-config-next` with a config, or record that linting is out of scope.
9. **Goal field in the plan API (future change).** Add experiment's Goal field is labeled "not sent": the plan API
   (`PlanRequest` in `backend/app/api.py`) has no goal, and the planner works toward the campaign's fixed goal. Sending
   the typed goal needs a backend change (a `goal` field on the request, used by the setup agent). Until then, keep
   the "not sent" label.
10. **Key status in the API (future change).** The banner says Claude replies are mocked when the newest run used
   mock replies, because the API does not report whether `ANTHROPIC_API_KEY` is set. Before any run it shows the
   default text. A small field on `/api/health` (for example `llm: "anthropic" | "mock"`) would make it exact.
11. **Diagnosis replies are cut off (backend, future change).** In a live run on 2026-11-22 (thread e2e-202158) the
   diagnosis agent called Claude for real, but its reply stopped at exactly 400 output tokens, the `max_tokens=400` in
   `backend/app/diagnosis.py`. The JSON was incomplete, so the code gate fell back to hold (INVALID_PROPOSAL). The
   outcome is safe, but the agent's own proposal is lost. Raising the limit or shortening the requested reason fixes it.

## Page content changes to review

12. **"What is MCP?" panel removed from the Architecture page.** Its live status line was kept and moved just above
    "Step details, read from the backend" (unchanged): "MCP tool gateway in this build: Active right now (FastMCP
    session)", or the direct-fallback wording, read from `/api/health`.
13. **Optimizer and prediction card gets one more line.** Requested: "Called through MCP, so a real optimizer can replace
    this mock without changing the setup agent." Corrected after checking the code, because the card covers two steps:
    "The optimizer is called through MCP, so a real optimizer can replace this mock without changing the setup agent.
    The prediction lookup is a plain function call." (In `graph.py` the optimizer node calls the `propose_alloy_ratios`
    tool through the MCP gateway, falling back to a direct call if the session fails; the setup agent only supplies the
    search space; `prediction_model.score` is called directly. A replacement must keep the tool's inputs and outputs and
    the element and route lists that `setup_agent.py` imports from `optimizer.py`.)
14. **Phoenix traces link in the header** (`NEXT_PUBLIC_PHOENIX_URL`, read when the console is built; unset means
    `http://localhost:6006`, empty hides the link; `render.yaml` sets the hosted address on `sdl-console-rr`). Its
    hover note says "Read-only login, ask for access", which is **not true yet**: Phoenix has no login (item 4).
    Protect Phoenix, or change the note in `lib/settings.ts` (`PHOENIX_TRACES_NOTE`), before sharing the link.

## Checks

15. **Backend tests pass:** `cd backend && .venv/bin/python -m pytest -q`.
16. **Frontend type check and build pass:** `cd frontend && npx tsc --noEmit && npm run build`.
17. **Backend unchanged by the branch:** `git diff --stat deploy...<branch> -- backend` prints nothing.
18. **No secrets in any commit on the branch:** scan every commit in `deploy..<branch>` for keys and secret files
    (Anthropic, Firebase/Google, AWS, GitHub, private keys, `.env`), not just the final files.
19. **Contrast:** text meets 4.5:1 and control borders 3:1 in both themes.
20. **Screenshots of every screen** in both themes at desktop and phone width, reviewed and approved.
21. **Example data stays labeled:** every item carries a LIVE or EXAMPLE tag, and the banner says Example data.
