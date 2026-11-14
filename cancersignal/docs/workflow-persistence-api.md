# Persistent demo workflow actions

Implemented in `feat/persistent-clinical-workflow`. Backend only; Agent B owns
frontend integration. All paths below are relative to `/api/v1`. This is a
synthetic demonstration system. Actor labels are **not authentication**, do not
establish a role or authorization, and are not a production medical audit trail.
Actions are explicitly submitted by humans. These records create no actual FIT
orders, referrals, prescriptions or external healthcare integrations. The LLM
neither selects nor submits a decision.

## Endpoints and contracts

| Method | Path | Success |
| --- | --- | --- |
| POST | `/analyses/{analysis_id}/dismissal` | 201, saved dismissal |
| GET | `/analyses/{analysis_id}/dismissal` | 200, saved dismissal |
| POST | `/review-requests/{request_id}/decision` | 201, saved decision |
| GET | `/review-requests/{request_id}/decision` | 200, saved decision |
| GET | `/review-requests?status=pending` | 200, existing response array |
| GET | `/review-requests?status=reviewed` | 200, completed review history |
| GET | `/review-requests?status=all` | 200, pending and completed requests |

The existing handoff POST and review detail GET remain available. Collection
`status` defaults to `pending`. `patient_id`, `limit` (1–200, default 100) and
`offset` (>=0, default 0) work with every status. Filtering precedes pagination.
Ordering remains urgent → review → normal, then handoff creation timestamp
ascending, then UUID ascending, including historical queries. It is not decision
time order. `reviewed` is the terminal/completed state; there is no separate
`completed` status or reopening endpoint. Existing response fields and the bare
array shape are preserved. The status union expands to `pending | reviewed`.

Dismissal request:

```json
{
  "patient_id": "11111111-1111-4111-8111-111111111111",
  "reason_code": "already_aware",
  "comment": "SYNTHETIC case: investigation documented in the original record.",
  "actor": "SYNTHETIC Nurse"
}
```

Dismissal response:

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "analysis_id": "22222222-2222-4222-8222-222222222222",
  "patient_id": "11111111-1111-4111-8111-111111111111",
  "reason_code": "already_aware",
  "comment": "SYNTHETIC case: investigation documented in the original record.",
  "actor": "SYNTHETIC Nurse",
  "created_at": "2026-11-14T12:00:00Z"
}
```

Reason codes map exactly to the four labels in `FindingsPanel.tsx`:

| Code | Existing UI label |
| --- | --- |
| `already_aware` | Physician already aware or investigation under way |
| `another_diagnosis` | Symptoms explained by another diagnosis |
| `patient_declined` | Patient declined further investigation |
| `other` | Other (explained in the record) |

`comment` is optional for all reasons, including `other`, whose UI label refers
to an explanation in the clinical record. When supplied it must contain a
non-whitespace character and be at most 4000 characters. `actor` is required,
nonblank and at most 120 characters; a demo role label is acceptable. Actor text
is unverified. Unknown fields, client timestamps and client status are rejected.
All IDs are UUIDs. Example IDs above are illustrative; use actual API IDs.

Decision request:

```json
{
  "action": "fit_ordered",
  "comment": "SYNTHETIC simulated action only.",
  "actor": "SYNTHETIC Physician"
}
```

Decision response:

```json
{
  "id": "55555555-5555-4555-8555-555555555555",
  "review_request_id": "33333333-3333-4333-8333-333333333333",
  "action": "fit_ordered",
  "comment": "SYNTHETIC simulated action only.",
  "actor": "SYNTHETIC Physician",
  "status": "reviewed",
  "created_at": "2026-11-14T12:01:00Z"
}
```

| Action | Existing UI result | Applicable request priority |
| --- | --- | --- |
| `fit_ordered` | FIT ordered | urgent or review |
| `referral_made` | Referral made | urgent or review |
| `no_action` | No action | urgent or review |
| `acknowledged` | Acknowledged | normal |

Applicability follows `PhysicianView.tsx`: routine requests show Acknowledge;
CancerSignal alerts show the other three actions. All successful decisions move
`pending` to `reviewed` atomically with saving the action. No clinical result or
analysis status is modified. Decision identity/comment limits match dismissal.

## Conflicts, history and errors

- **404:** unknown analysis/request/action; dismissal patient does not match the
  exact analysis. GET dismissal/decision returns 404 when no action exists.
- **409:** duplicate or conflicting dismissal/decision, review already completed,
  action inapplicable to priority, attempted dismissal after handoff, or handoff
  after dismissal. No previous action is overwritten. As before, incomplete,
  failed, error-marked or invalid-evidence analyses cannot enter the workflow.
- **422:** invalid UUID, reason/action/status, blank or oversized actor/comment,
  extra request fields or invalid pagination. FastAPI returns validation details.
- **503:** database operation unavailable, via the existing API error handler.

Other errors use `{"detail": "..."}`. Both identical and different repeated
**action** POSTs return 409. Fetch the saved action after a 409 or an ambiguous
network failure to reconcile; never silently claim that a different action won.
The original **handoff** POST still returns 201 on creation or 200 with the
original request on retry, including its reviewed status after a decision.

Actions are append-only through this API: no edit/delete/reopen routes. The
minimal history is one final event per analysis/request, retained across all
subsequent analyses of the patient. GET the patient's analyses and their exact
ID-scoped dismissals; use the review collection with `status=all` or `reviewed`
and fetch each request's decision for previous physician actions. A new analysis
never inherits an earlier analysis's dismissal or decision. Existing provenance
and evidence checks on review list/detail remain unchanged.

Row locks serialize dismissal and handoff against the same analysis, and decisions
against the request. Database uniqueness protects one dismissal per analysis and
one decision per request. Foreign keys protect request references and composite
analysis/patient ownership. Timestamps come from PostgreSQL. These are API
immutability guarantees, not tamper-proof storage against direct database writers.

## Agent B: exact frontend integration requirements

1. Retain backend analysis UUIDs and review request UUIDs. Replace patient-keyed
   `dismissedFor` with analysis-keyed state. Never substitute a patient's newest
   analysis during a dismissal submission or retry.
2. Add POST/GET helpers for the four action endpoints above in `lib/api.ts`.
   Map labels to codes using the tables above. Supply the displayed demo actor,
   optionally a comment. Do not send patient ID as the review request ID.
3. Await a successful POST before showing a saved dismissal/decision. On failure,
   keep the case unresolved and show the error. On 409/ambiguous network failure,
   GET the saved action and display its actual actor/action/time.
4. On loading an analysis, GET its dismissal. A 404 means not dismissed; other
   errors are failures to load state. After success, use the server reason and
   timestamp instead of the existing simulated log text.
5. Restore sent state with `/review-requests?patient_id={id}&status=all`, keyed by
   analysis ID. Using the default pending-only collection loses completed sends.
   Paginate when needed; max page size is 200.
6. Load the physician active queue with `status=pending`. On decision success,
   remove that request from the pending queue and fetch reviewed history if shown.
   Fetch `/review-requests/{id}/decision` to restore its action after refresh.
   Keep server queue order and expand API status types to `pending | reviewed`.
7. Enable Acknowledge only for `normal`; enable FIT/referral/no-action for
   `urgent`/`review`. Prevent dismissal of sent cases and sending dismissed cases.
   These are server-enforced transitions, not only UI conventions.
8. Keep synthetic/prototype fallback entries separate; do not POST invented IDs.
   Label saved actions as simulations, never real medical orders/referrals.

No frontend file is changed here. The additive API is ready; wiring these calls
and restoring UI state remains Agent B's work. No unresolved backend contract
change is required. Review status widening and the explicit code mapping above
are the frontend type/behavior changes to incorporate.

## Migration and validation

From `cancersignal/backend/`, with the intended PostgreSQL environment configured:

```sh
python -m alembic upgrade head
python -m alembic check
RUN_DATABASE_TESTS=1 python -m pytest tests/test_reviews.py tests/test_workflow.py -q
```

Use the project's virtualenv Python. `workflow_0001` follows `review_0001`, creates
`alert_dismissals` and `physician_decisions`, and expands the review status check.
No clinical tables, seed/reset code or existing records are changed. Coordinate
any other migration branch before integration; this worktree has one head.
Downgrade is supported on empty action tables. It deliberately refuses downgrade
with saved actions or reviewed requests to prevent silently deleting history;
archive and plan a rollback explicitly for a populated deployment.

Validation on 2026-11-14: **52 PostgreSQL integration tests passed** across the
existing review and new workflow suites. Tests create their own disposable
database, exercise upgrade → downgrade → upgrade, and compare the migrated schema
with SQLAlchemy metadata. They cover every reason/action, errors, ownership,
new-session refresh, unchanged original analysis/evidence/history, pending and
reviewed queries, and true separate-connection dismissal/decision/handoff races.
The application database was not migrated or seeded by this implementation task.

Full backend regression result: **511 passed in 17.03s**, with
`RUN_DATABASE_TESTS=1` and real PostgreSQL enabled. The public OpenAPI route
allowlist was updated for the two new resources. `git diff --check` passed and
`alembic heads` reports only `workflow_0001`. Local network sandbox restrictions
required running PostgreSQL tests with elevated execution permissions; the first
successful database run exposed a migration constraint-naming issue, which was
fixed before these passing results. No mocked database result is counted here.

## Reviewed integration — 2026-11-14

Reviewed all 16 workflow files against integration commit `160d3c8`; there were
no overlapping edits. Review found that the concurrent demo reset implementation
would violate the new foreign keys after actions were saved. With explicit user
approval, its cleanup now removes decisions scoped through the selected demo
patients' reviews and removes their dismissals before deleting parent records.
A regression test verifies repeated reset and preservation of unrelated patients'
workflow records. No reset was performed against the application database.

The isolated integration candidate passed **532 tests, 1 skipped**. After applying
the reviewed changes and minimal reset fix to the actual
`integration/analysis-end-to-end` working tree, the full backend suite again
passed **532 tests, 1 skipped in 23.14s**, with real PostgreSQL enabled and paid
live inference disabled. The skipped test is the explicit live inference test.
`git diff --check` passed; Alembic still has the single `workflow_0001` head.

Changes are integrated as uncommitted working-tree changes, respecting the
original no-commit instruction. No Git merge commit or push was performed; these
are post-integration test results, not a claim of testing a committed merge.
Existing unrelated edits were preserved. The application database still requires
`alembic upgrade head` before serving the new API.
