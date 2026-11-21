# Before merging radical-ui into deploy

Work through this list in order. Merge only after the owner approves, as one merge, with the exact steps written down
first.

1. **Remove the temporary theme switch.** Delete `frontend/components/ThemePreview.tsx`, remove its import and
   `<ThemePreview />` from `frontend/app/layout.tsx`, and remove `suppressHydrationWarning` from `<html>` there.
   Then choose the default theme with `DEFAULT_THEME` in the same file.
2. **Decide on ESLint.** The frontend has no ESLint installed or configured, so `next build` only type-checks. Either
   add `eslint` and `eslint-config-next` with a config so the build really lints, or record that linting is out of
   scope.
3. **Backend tests pass:** `cd backend && .venv/bin/python -m pytest -q`.
4. **Frontend type check and build pass:** `cd frontend && npx tsc --noEmit && npm run build`.
5. **Backend unchanged by this branch:** `git diff --stat deploy...radical-ui -- backend` prints nothing.
6. **No secrets in any commit on the branch:** scan every commit in `deploy..radical-ui` for keys and secret files
   (Anthropic, Firebase/Google, AWS, GitHub, private keys, `.env`), not just the final files.
7. **Contrast:** text and button colors meet WCAG AA (4.5:1 for normal text, 3:1 for large text and UI parts) in
   both themes.
8. **Screenshots of every screen** in both themes at desktop and phone width, reviewed and approved.
9. **Example data stays labeled.** The Customer queue and Internal experiments keep their Example data banner.
