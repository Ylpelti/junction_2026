# Demo dataset mismatch investigation — 14 November 2026

## Exact root cause

The local frontend on port 3000 was running from
`/Users/joonavanska/junction_2026/cancersignal/frontend`, on branch
`integration/analysis-end-to-end` at `160d3c8`. Its process cwd was verified with
`lsof`. The API processes on port 8000 used that checkout's backend. The frontend
integration already published as `9052a2e` was not what the local server served.
Current remote main was `845e237` (the integration plus README changes).

The served JavaScript used the default API origin `http://localhost:8000`, with
`/api/v1` appended. There was no frontend environment override. The old frontend
initialized `source` to `backend`, but appended fallback routine items even in
backend mode and offered browser-only queue contents during failures or when
CancerSignal was disabled. Its live queue expression was:

```ts
[...backendQueue.data, ...demoItems.filter(x => !x.cs), ...localSent]
```

Thus **Lehtonen Juha (`q2`) and Salminen Emma (`q3`) were frontend fallback items**.
They were absent from the actual FastAPI patient and review collections.

**The Nieminen FIT result was not solely a browser fallback.** Although
`frontend/data/fallback.ts` also contains `Nieminen Pertti` (`CS-4501`) with a
canned FIT of 48 µg/g, a corresponding older synthetic scenario is persisted in
this database. Read-only GET requests returned:

| Record | Actual persisted identifier |
| --- | --- |
| Legacy patient `SYNTHETIC Nieminen Pertti` | `9e6f8a99-3d15-57b6-9fe3-26385fc9e641` |
| Pending review request, priority `urgent` | `188229ec-b634-4585-b54d-46404d6957ae` |
| Saved analysis | `10338d63-e686-45d8-b8de-287633bdcdcc` |
| Completed FIT observation | `60194209-a78d-53f5-ae0e-2b6c7dc0724e` |
| Abdominal-pain source observation | `5786937e-7a94-5f1b-9037-31c4264fb294` |

That FIT source has code `F-HB-FIT`, value `48.000000`, unit `ug/g`, and status
`completed`. It belongs to the legacy patient UUID. The saved analysis has two
triggered rules (SUO-08 and SUO-06) among ten rule results. Its stored Finnish
explanation includes all ten rule statements; the prior explanation component
rendered every statement without checking the actual trigger result.

The actual API contained **16 patients**, including both canonical and legacy
synthetic records. The canonical fixture has only these four patient IDs:

| Canonical patient | UUID | Observations at inspection |
| --- | --- | --- |
| SYNTHETIC Laine | `138fff92-bea8-5f85-a95a-5fb502fd9e57` | 9 |
| SYNTHETIC Nieminen | `9f1864d7-0a2b-55d2-a007-7f886ab65b2e` | 12 |
| SYNTHETIC Heikkinen | `53bcac07-8145-5a0a-bcf9-a64720ceecac` | 11 |
| SYNTHETIC Korhonen | `6fa564bb-9001-5226-b01e-2fbb61cc4526` | 9 |

Canonical Nieminen's laboratory history has Hb values 148, 139, 128 and 125 g/L;
there is no FIT observation in that patient's returned history. No findings are
hardcoded from this comparison. The canonical source fixture was read, not edited.

Brave's current client-side selection could not be directly read because macOS
computer-use permission remained unavailable even after the user authorized
Brave use. The running process, served bundle and actual API records were verified
independently; no claim is made about the user's exact pre-existing tab selection.

## Fix

Changes are isolated on `fix/canonical-demo-isolation`, based on `845e237`, in
`/private/tmp/cancersignal-dataset-fix`.

- Backend demo collections include only the canonical UUID registry. A test
  compares the registry to `backend/app/db/demo_data/patients.json`. The registry
  contains only membership IDs, never clinical fixtures or expected outcomes.
- Filtering occurs after pagination. Review order, request UUIDs, analysis UUIDs,
  evidence and backend-derived priority are preserved. Non-UUID mock requests and
  mismatched patient/analysis/source relationships fail closed.
- Prototype mode remains explicit and visibly labelled. Mode changes clear queue
  history and errors; delayed responses cannot introduce another dataset.
  Turning CancerSignal off does not enable fallback queue entries.
- Physician cards start with the stored Finnish summary and up to three stored
  Finnish finding statements. Full statements and exact sources remain available.
- Rule explanation statements join to **trigger_rule_id** from triggered results;
  unmatched/non-triggered statements are omitted, never inferred from prose.
- Technical references, validation limitations and provider warnings are expandable.
  Numeric display removes insignificant trailing zeros, uses Finnish decimal commas,
  and displays `ug/g` as `µg/g`, without rounding or changing magnitudes. Original
  values, units, source text and timestamps remain available in evidence details.
- The physician view loads actual full observation histories to show recorded
  completed investigations and FIT results. Actions are under an explicit simulated
  decision disclosure, labelled as choices rather than recommendations. If a FIT is
  already completed, its action is explicitly labelled as a **repeat** FIT chosen
  by the clinician. No need to repeat a test, referral or medical decision is inferred.

No canonical seed, migration, clinical model, mathematical rule, extraction pipeline,
backend endpoint or frontend design-system file was changed. The shared database
was inspected only with GETs; its legacy records remain intact.

## Verification

- Typecheck and webpack production build: passed.
- `npm test`: **24 passed**, including 7 new dataset/content tests. Coverage includes
  mixed canonical/legacy API responses; prototype IDs and mock queue IDs; mode
  switches and CancerSignal-off behavior; mismatched source ownership; triggered
  rule matching; exact numeric formatting; completed-FIT context; and prior workflow
  persistence/network/patient-isolation regressions.
- `tests/run_real_e2e.py`: **passed with real FastAPI + disposable PostgreSQL**.
  The test database deliberately includes the existing legacy seed, the canonical
  seed and a real persisted legacy review request. Canonical nurse handoff, physician
  decision, dismissal and refresh work; the legacy request stays stored and excluded.
  The disposable database is removed by the harness. No live provider calls.
- After replacing only the stale frontend process, the production build is serving
  **http://localhost:3000** from the fix worktree, using the existing API at
  `http://localhost:8000`. The API process was not restarted.
- `running-demo.spec.ts`: **passed against those running services**, with every API
  write blocked by the test. Exactly four canonical patients are shown. The actual
  canonical physician queue is empty because the one saved request belongs to legacy
  Nieminen Pertti. No substitute queue entries or handoffs were invented.
- Running-page screenshot inspected. `git diff --check` passed.

Read-only running-demo check (from `cancersignal/frontend`):

```sh
E2E_RUNNING_URL=http://localhost:3000 E2E_API_URL=http://localhost:8000 \
  npx playwright test running-demo.spec.ts
```

Use `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to select an installed compatible browser if
needed. The existing Playwright setup otherwise supports `npx playwright install
chromium`. The original dirty checkout was preserved; restarting its old frontend
would reintroduce the old behavior. Start the fixed frontend from this worktree.
Publication of these verified fixes to `main` was subsequently authorized by the user.
