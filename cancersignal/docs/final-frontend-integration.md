# Final frontend integration — 14 November 2026

Implemented on `integration/final-frontend`, based on fetched `origin/main`
`025a9ea`, in `/private/tmp/cancersignal-final-frontend`. Publication to `main`
was subsequently authorized by the user after verification.
The original checkout and its uncommitted backend/package-lock work were preserved.
Remote frontend history was checked: `origin/codex/public-dynamic-demo` has an
additional same-origin deployment proxy, but no newer component design. That
separate deployment change was not copied into this integration branch.

## Implemented

- API patient loading and complete paginated observation, analysis and review
  histories. Original observation metadata is retained; source details display
  UUIDs, note text, event/recording timestamps, codes, values, units, encounter
  references and statuses. Live mode has no fabricated appointment/queue fillers.
- New notes are saved once, then analysed using `note_observation_id`. The existing
  pipeline remains responsible for findings, rule priorities and numerical results.
  Refresh reads saved analyses without generating explanations or invoking an LLM.
- Saved-analysis selection restores exact analysis-scoped handoffs and dismissals,
  including older runs. A new run does not inherit an earlier action.
- Persistent dismissal reasons and physician decisions, with demo actors and actual
  server timestamps. POST conflicts/lost responses read back the actual saved action,
  including when another actor saved a different action. Only GET 404 means absent.
- Pending physician queue preserves server order; reviewed history restores saved
  decisions and has no action buttons. Normal requests show Acknowledge, while
  review/urgent requests show FIT/referral/no-action simulations.
- Finnish structured explanations, source evidence and backend mathematical text;
  fallback explanations and missing-data limitations remain visible. QCancer is
  separate research output; missing inputs never become a fabricated probability.
- Loading/error states, action locks, stale patient-response protection, explicit
  prototype mode, and saved-history reconciliation after an ambiguous note POST.
  The existing layout, typography and visual component design are retained.

## Verification

| Stage | Static inspection | Mocked tests | Real HTTP / PostgreSQL | Chromium interaction |
| --- | --- | --- | --- | --- |
| Patient selection/history | Yes | Pagination, metadata, isolation | Four canonical fixture patients | Select Laine; four patients visible |
| Note save and analysis | Yes | UUID contract, lost response, duplicate lock | Real note and analysis POSTs | Enter and save two notes |
| Findings/evidence/explanation/QCancer | Yes | Mapping and rendered output | Saved pipeline responses | Open Finnish explanation and source details; insufficient-data state |
| Nurse handoff | Yes | Submit/reload | Persistent review request | Submit, reload and reopen |
| Physician decision and queue | Yes | Submit/reload, pending removed | FIT decision readback; reviewed status | Decide, reload, reviewed history |
| Dismissal and older actions | Yes | Submit/reload, GET failure | Separate analysis dismissal | Dismiss, reload, select older sent analysis |
| Conflicts and failures | Yes | 409, network/readback, stale responses | Existing backend race/contract tests | Mocked failure and lost-note interactions |

Executed checks:

- `npm run typecheck` — passed.
- `npm run build -- --webpack` — passed.
- `npm test` — **17 passed**: 9 API/mapping/render tests and 8 mocked Chromium
  workflow tests. No backend is needed for these tests.
- Backend `tests/test_api_contract.py tests/test_workflow.py tests/test_reviews.py`
  with `RUN_DATABASE_TESTS=1` — **53 passed**, using a disposable PostgreSQL DB.
- `tests/run_real_e2e.py` — **1 real Chromium E2E passed**, with real Uvicorn,
  migrations, canonical four-patient seed and rules in a newly created PostgreSQL
  database. The harness stops its services and drops only that database afterward.
- Browser screenshot inspected; existing design remains intact. A discovered
  active-patient reselection bug was fixed and covered by a regression test.
- `git diff --check` — passed.

Initial local setup attempts encountered missing worktree configuration, sandbox
TCP restrictions and a Playwright browser-version mismatch. The final checks used
read-only access to the existing ignored environment configuration, authorized
local networking, and the already-cached Chromium binary. No shared application
migration, seed, reset or clinical action was performed.

## Reproduce

From `cancersignal/frontend`:

```sh
npm ci
npx playwright install chromium
npm run typecheck
npm test
# Run with the backend virtualenv Python and PostgreSQL role with CREATEDB:
../backend/.venv/bin/python tests/run_real_e2e.py
npm run build -- --webpack
```

The browser harness uses frontend port 3107 and a dynamically chosen API port.
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` may select an existing compatible Chromium binary.
Normal application configuration still uses `NEXT_PUBLIC_API_URL` and backend CORS.
The shared application needs the already-existing `workflow_0001` migration before
these workflow endpoints can be used; this task deliberately did not migrate it.

## Limits and precise contract gaps

- Real E2E used extraction `off`, deterministic Finnish explanations and retrieval
  `auto`. It verifies integration with real structured clinical facts, not live
  provider extraction of arbitrary prose, hybrid embedding quality or clinical
  accuracy. Live inference remains opt-in and was not exercised.
- The note-create API accepts no idempotency key. An unconfirmed attempt is retained
  in this tab's session storage and blocks another note POST, including across
  refresh. Reconciliation matches its patient, exact text and timestamp, then uses
  the confirmed note UUID. If no note can be confirmed, the UI deliberately stays
  blocked rather than claiming absence or blindly resending. Closing the tab or
  clearing browser storage loses this recovery record; server idempotency is needed
  for a cross-session guarantee. No endpoint was added.
- Analysing a saved note can create another run by the existing backend contract.
  Recovery first reads existing runs; the user should wait for an outstanding
  request to finish before explicitly selecting Analyse saved note. The API has
  no atomic “get or create analysis for note” operation.
- This is a synthetic simulation. Saved FIT/referral actions do not create real
  clinical orders. Demo actors are labels, not authentication.
