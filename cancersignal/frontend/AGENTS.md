# Frontend instructions

Inherit `../AGENTS.md`. Paths below are relative to `frontend/`.

## Current UI and integration

- Next.js App Router entry points are in `app/`; `components/CancerSignalApp.tsx`
  coordinates nurse/physician views, demo controls and workflow state.
- `lib/api.ts` owns API calls, `lib/mappers.ts` translates backend fields,
  `lib/types.ts` defines UI types and `lib/flags.ts` documents fallback switches.
  Read `../docs/contracts.md` and `../docs/physician-review-api.md` before changes.
- Nurse note saving can run analysis or use the current-practice path. Findings
  resolve source chips through returned observations; do not fabricate references.
- Deterministic triggered rules alone set review alerts. Urgent rules take
  precedence; absent priority defaults to review. QCancer predictions are shown
  separately, including missing-input status, and never route patients.
- Failed, pending or running analysis is unavailable, not a negative result.
  Preserve the unavailable state when the backend cannot be reached.
- Review submissions, dismissals and physician decisions persist through the
  workflow API, scoped to analysis/request UUIDs. Only GET 404 means absent;
  conflicts and lost responses require readback. Display saved server timestamps.
- Backend demo mode uses only the four canonical UUIDs from `lib/demo-dataset.ts`,
  checked against the backend fixture by regression tests. API histories, analyses
  and pending/reviewed queues preserve patient ownership and server ordering.
  Prototype fixtures and browser-only actions require explicit prototype mode.
  Do not silently substitute fixtures when the API fails.
- Physician summaries use saved Finnish text and only triggered rule explanations;
  technical warnings remain expandable. Completed tests do not imply repeat orders.
  See `../docs/demo-dataset-isolation.md` for the running-demo investigation.
- Keep numeric clinical calculations in Python. Do not infer lab reference
  ranges, abnormal flags, missing facts or risk cutoffs in the UI.

## Commands

From this directory, with Node.js 22+:

```sh
npm ci
npm run dev
npm run typecheck
npm run build
# Serve the completed production build:
npm start
```

If the environment blocks Turbopack's build-worker port, use
`npm run build -- --webpack`. Playwright covers API/mapping tests and mocked browser interactions (`npm test`).
Install Chromium with `npx playwright install chromium`; an existing binary can
be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. From this directory, run the
backend virtualenv Python on `tests/run_real_e2e.py` for real FastAPI + disposable
PostgreSQL browser verification. It never migrates or resets the shared database.
See `../docs/final-frontend-integration.md` for results and contract limitations.

The default backend origin is `http://localhost:8000`. Set `NEXT_PUBLIC_API_URL`
in `.env.local` to another origin without `/api/v1`, then restart/rebuild Next.js.
Configure backend `CORS_ORIGINS` for the frontend origin. Do not put secrets in
`NEXT_PUBLIC_*` variables.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
