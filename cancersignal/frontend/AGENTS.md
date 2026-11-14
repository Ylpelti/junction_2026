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
- Backend review submissions and the pending physician queue are connected.
  Dismissals and physician decisions remain local state; backend-item decisions
  must remain visibly unsaved. Do not imply local state survives reloads.
- Appointment details, routine queue items and the selectable prototype dataset
  still have fallbacks. Keep synthetic prototype results clearly labelled and
  inspect `lib/flags.ts` before changing fallback behavior.
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
`npm run build -- --webpack`. No frontend test runner is configured. Verify
changed interactions in the browser when available, especially note saving,
alerts/evidence, physician submission and failures; report checks actually run.

Next.js rewrites same-origin `/api/v1/*` requests to the backend. Local
development defaults to `http://localhost:8000`; set `NEXT_PUBLIC_API_URL` in
`.env.local` to another backend origin when needed. Production hosting may set
`CANCERSIGNAL_API_INTERNAL_HOSTPORT` so the Next.js server proxies over a private
network. Do not put secrets in `NEXT_PUBLIC_*` variables.
