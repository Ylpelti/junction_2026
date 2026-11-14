# Physician review handoff API

Persist a nurse's request to review an **existing completed analysis**. This does
not rerun analysis or create a physician decision, referral, recommendation,
investigation order or referral draft. Frontend implementation is unchanged.

## Setup

From `cancersignal/`, start PostgreSQL with `docker compose up -d db`. Then:

```sh
cd backend
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload
```

Migration `review_0001` follows `rag_0001` and adds only
`physician_review_requests`: UUID, patient/analysis references, pending status,
server-derived priority, creation time and optional `submitted_by`. A composite
foreign key enforces patient/analysis ownership; a unique analysis key prevents
duplicates, including concurrent submissions. Findings and evidence stay in their
original tables. Reads reuse `PatientRead` and `AnalysisResponse` without storing
duplicate analysis JSON.

## Endpoints

All paths use `/api/v1`.

| Method | Path | Result |
| --- | --- | --- |
| POST | `/patients/{patient_id}/review-requests` | 201 new; 200 with the original request on retry |
| GET | `/review-requests` | Pending requests, ordered urgent → review → normal, oldest first, then UUID |
| GET | `/review-requests/{request_id}` | Request with patient, original analysis, findings and evidence |

POST body (use real IDs returned by the running API):

```json
{
  "analysis_id": "22222222-2222-4222-8222-222222222222",
  "submitted_by": "Nurse H. Virtanen"
}
```

Response shape; the existing nested objects are **abbreviated** here:

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "patient_id": "11111111-1111-4111-8111-111111111111",
  "analysis_id": "22222222-2222-4222-8222-222222222222",
  "status": "pending",
  "priority": "review",
  "created_at": "2026-11-14T12:00:00Z",
  "submitted_by": "Nurse H. Virtanen",
  "patient": {"id": "11111111-1111-4111-8111-111111111111", "synthetic_name": "SYNTHETIC Example"},
  "analysis": {"id": "22222222-2222-4222-8222-222222222222", "status": "completed", "findings": [], "trigger_results": [], "source_observations": []}
}
```

Full nested fields are the existing schemas in `/docs` and
[contracts.md](contracts.md). POST returns a `Location` header pointing to the
detail endpoint. Retries preserve the original ID, timestamp, identity and
priority. Separate analyses of one patient can each have a request.

GET collection returns an array. Parameters: `status=pending` (the only supported
status), optional `patient_id`, `limit` (default 100, max 200), `offset` (default
0). Filtering and ordering precede pagination.

Priority is snapshotted from saved **triggered deterministic rule results**:
any urgent match → `urgent`; other matches → `review`; no matches → `normal`.
The last case permits an explicit human handoff without inventing an AI alert.
LLM prose/client-supplied urgency cannot assign priority. Later rule edits do not
change saved review priority or existing analysis rule snapshots.

Errors follow the existing `{"detail": "..."}` convention:

- **404:** unknown patient, request or analysis; also another patient's analysis.
- **409:** pending/running/failed or error-marked analysis, missing input-note or
  cutoff provenance, invalid/unavailable evidence. No request is saved.
- **422:** malformed body/query/UUID, extra fields such as `priority` or
  `decision`, blank identity or identity longer than 120 characters.
- **503:** database unavailable; constraint conflicts use the existing 409 handler.

Completed analyses can have missing-information **warnings**, which remain
visible in `analysis.provenance.missing_information`. These do not imply a failed
execution. Runs later marked failed/incomplete disappear from the actionable
list; detail reads return 409. Source IDs, patient/time scope, quotes and offsets
are rechecked. Corrupt evidence causes a 409 on list/detail reads rather than
show unverified findings as actionable. `submitted_by` is an unverified demo
label, not authentication. There are no decision/update/delete endpoints.

## Frontend integration instructions

1. **Keep the analysis ID.** In `CancerSignalApp.tsx`, preserve the raw
   `ApiAnalysisResponse.id` alongside the visit result when saving a note.
   `toAnalysis()` currently drops it. Do not submit patient IDs or display IDs
   such as `F1` as analysis IDs.
2. **Add API calls.** In `lib/api.ts`, use the existing `request()` helper for
   POST `sendReviewRequest(patientId, analysisId, submittedBy?)`, GET
   `listReviewRequests()` and optionally GET `getReviewRequest(id)`. Treat 201
   and 200 as success. Submit only persisted backend analyses, not prototype IDs.
3. **Persist send state.** Make `sendToPhysician` await POST; mark sent only on
   success. Show errors and allow retry with the same analysis ID. Restore sent
   state using `/review-requests?patient_id={patientId}` after reload. Track
   submissions by analysis, since one patient can have several analyses.
4. **Load the queue.** Fetch `/review-requests?status=pending` on opening/refreshing
   the physician view and after sending. Replace `sentItems`/fallback entries for
   the backend view. Preserve API order; sorting displayed `HH:mm` strings loses
   ordering across dates.
5. **Map existing UI fields** in `lib/mappers.ts`:

| `QueueItem` field | Mapping from API request `r` |
| --- | --- |
| `key` | `r.id` |
| `name`, `demo` | From `toPatient(r.patient, undefined)` |
| `time` | Display `r.created_at` locally; retain ISO time for dates |
| `from` | `r.submitted_by ?? "Not recorded"` |
| `level` | `r.priority` directly, including `normal` |
| `cs` | `r.priority !== "normal"` |
| `summary` | `r.analysis.explanation` |
| `findings` | Pick `id/title/rule/ruleSrc` from `toAnalysis(r.analysis).findings` |

Retain `patient_id`/`analysis_id` for opening a saved case. Full findings, quotes
and original records are in `r.analysis`; use observation UUIDs for evidence
navigation. Fetch the input note with existing `GET /observations/{id}` using
`analysis.provenance.input_observation_id` if it is not a cited source.

Only send/list/detail become persistent. Do not disable all `USE_LOCAL_WORKFLOW`
behavior blindly: dismissal and physician decisions still have no API. Disable
physician action buttons for backend queue items until their workflow exists;
browser-only decisions must not be presented as saved. Prototype/fallback
behavior can remain separate and clearly labelled.

## Tests

From `backend/`, with PostgreSQL reachable:

```sh
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest tests/test_reviews.py -q
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest -q
```

The test fixture creates, upgrades, downgrades, upgrades and drops only a newly
named disposable database. Tests use synthetic data, including true concurrent
submissions, with no LLM calls or physician decisions.
