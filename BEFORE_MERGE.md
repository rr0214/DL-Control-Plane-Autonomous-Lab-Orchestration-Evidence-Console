# Before merging (radical-ui or scientist-app-v2 into deploy)

Work through this list in order. Merge only after the owner approves, as one merge, with the exact steps written down
first.

## Temporary items to remove

1. **The theme query switch.** Delete `frontend/components/ThemePreview.tsx`, remove its import and `<ThemePreview />`
   from `frontend/app/layout.tsx`. It lets `?theme=dark` or `?theme=light` in the URL override the theme, for
   screenshots. The real theme switch in the header (saved in the browser) stays, and so does the small script in
   `layout.tsx` that applies it before the first paint (that script is why `suppressHydrationWarning` is on `<html>`).
2. **Screens index and theme preview page.** None were added on this branch. If one is added later, list it here.
3. **Anything else added only for testing.** Nothing in the repo: the screenshot and walkthrough tooling lives outside
   it. The `data-row` and `data-id` attributes on list rows and detail panels are used by that tooling; they are
   harmless and can stay.

## Decisions still open (flagged, not changed)

4. **Phoenix has no password.** Anyone with the Phoenix URL can read traces, including prompts and replies.
5. **Real Radical logo and brand assets.** The header uses a text wordmark ("Radical"); no logo is drawn or copied.
6. **Lab check rules**, including the 5% near-limit margin (`frontend/lib/labCheck.ts`, `LAB_LIMITS`).
7. **The prototype banner** is on (`SHOW_PROTOTYPE_BANNER` in `frontend/lib/settings.ts`). Decide whether it stays on
   for the hosted demo.
8. **ESLint.** The frontend has no ESLint installed or configured, so `next build` only type-checks. Either add
   `eslint` and `eslint-config-next` with a config, or record that linting is out of scope.

## Checks

9. **Backend tests pass:** `cd backend && .venv/bin/python -m pytest -q`.
10. **Frontend type check and build pass:** `cd frontend && npx tsc --noEmit && npm run build`.
11. **Backend unchanged by the branch:** `git diff --stat deploy...<branch> -- backend` prints nothing.
12. **No secrets in any commit on the branch:** scan every commit in `deploy..<branch>` for keys and secret files
    (Anthropic, Firebase/Google, AWS, GitHub, private keys, `.env`), not just the final files.
13. **Contrast:** text meets 4.5:1 and control borders 3:1 in both themes.
14. **Screenshots of every screen** in both themes at desktop and phone width, reviewed and approved.
15. **Example data stays labeled:** every item carries a LIVE or EXAMPLE tag, and the banner says Example data.
