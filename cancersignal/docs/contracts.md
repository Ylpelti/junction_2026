# Public API and internal pipeline contracts

This synthetic-data prototype uses the existing [storage model](data-model.md).
Pydantic in `app/schemas/records.py` and `app/schemas/analysis.py` is the source of
truth for `/openapi.json` and `/docs`. No diagnosis, cancer probability, or automatic
referral is produced. No frontend changes are included.

For the next component handoffs, use the versioned [shared contracts package](../backend/app/contracts/README.md).
It separates RAG from numerical history, polarity from temporal state, and
three-state rule outcomes from booleans. API v1 below remains compatible; the
rich handoff schemas are not automatically persisted or exposed over HTTP.

## Public REST endpoints

All paths below use the prefix `/api/v1`. `/health` remains unchanged.

| Method | Path | Request → response |
| --- | --- | --- |
| GET | `/patients` | `PatientRead[]` |
| POST | `/patients` | `PatientCreate` → `PatientRead` (201) |
| GET | `/patients/{patient_id}` | `PatientRead` |
| GET | `/patients/{patient_id}/encounters` | `EncounterRead[]` |
| GET | `/patients/{patient_id}/observations` | `ObservationRead[]` |
| POST | `/patients/{patient_id}/observations` | `ObservationCreate` → `ObservationRead` (201) |
| GET | `/observations/{observation_id}` | `ObservationRead` |
| GET | `/patients/{patient_id}/timeline` | `TimelineEvent[]` |
| POST | `/patients/{patient_id}/analyses` | `AnalysisRequest` → `AnalysisResponse` (201) |
| GET | `/patients/{patient_id}/analyses` | Saved `AnalysisResponse[]`, newest first |
| GET | `/analyses/{analysis_id}` | Saved `AnalysisResponse` |

Lists accept `limit` (default 100, max 200) and `offset` (default 0). Observations
and timeline accept `observation_type`, exact `code`, inclusive `date_from` and
exclusive `date_to` on event time. Date-time filters require a timezone and a valid
increasing range. Timeline events contain `event_type`, `occurred_at`, and either
`encounter` or `observation`; the other field is null. Observation type/code filters
apply to observations; encounter events use the date range only. Pagination follows
the chronological merge, with deterministic type/UUID tie breaks.

Patient names must begin with `SYNTHETIC ` (case insensitive). Observation bodies
reuse `ObservationCreate`, including `patient_id` matching the path and an optional
encounter belonging to that patient. IDs, text, timestamps, codes and values are
preserved; Decimal values serialize as strings. There are no update/delete or
encounter-creation endpoints. No authentication is implemented. Patient-path
operations enforce ownership; global observation/analysis UUID routes resolve
records directly. CORS permits local frontend origins on localhost/127.0.0.1:3000.

Reads return 200, creates 201, missing resources 404, invalid input/ownership 422,
ID/constraint conflicts 409, and database failures 503. Errors have `detail`;
FastAPI validation errors use a structured detail list. A foreign patient's input
note returns 404. Driver/provider errors and clinical text are not exposed in errors.

## Analysis request and response

POST executes synchronously. Supply exactly one input:

```json
{"note_observation_id": "UUID-of-an-existing-clinical-note"}
```

or a new note using the existing observation contract:

```json
{
  "note": {
    "patient_id": "UUID-matching-the-path",
    "observation_type": "clinical_note",
    "text": "SYNTHETIC source note for review.",
    "observed_at": "2026-05-01T12:00:00Z",
    "recorded_at": "2026-05-01T12:05:00Z"
  }
}
```

Responses include `id`, `patient_id`, `created_at`, `status`, `findings`,
`trigger_results`, `source_observations`, `explanation`, and `provenance`.
Findings reuse `current/historical/resolved/negated/uncertain` rather than introducing
the illustrative `documented` status. They include uncertainty and evidence UUIDs,
verbatim excerpts and optional `[start,end)` Unicode character offsets. Trigger
results include rule UUID/name/version/source, demonstration label, boolean outcome,
explanation, supporting UUIDs, recommended action and clinician-review flag.
`source_observations` resolves every evidence reference to the original record.

Provenance stores input-note UUID, cutoff, selected history UUIDs, retrieval/extraction
versions, rule metadata snapshots, `missing_information`, and optional `error_code`.
**201 means a run was saved; check its status.** Controlled pipeline failures persist
as `failed` with no partial findings/results. Unexpected adapter exceptions use
`pipeline_execution_failed`. Database errors roll back the request and return
409/503. A valid new source note is saved with a completed or failed run. GET never
reruns the pipeline. Negative rule results say “no signals identified.”

## Internal Python interfaces

Routes call database-backed `services/`; request-scoped SQLAlchemy sessions and
existing models perform all storage. Analysis does not overwrite source records.
`api.dependencies.get_analysis_pipeline()` supplies a replaceable `AnalysisPipeline`:

```python
retrieve_context(patient_id, query, db_session, *, before) -> RetrievedContext
extractor.extract(context, note: ObservationRead) -> ExtractionResult
evaluate_triggers(patient_id, findings, rules: list[TriggerRuleRead]) -> list[TriggerEvaluation]
```

The baseline retriever filters patient ID and both `observed_at < before` and
`recorded_at < before` before lexical-overlap/recency ranking. It includes original
observations, timestamps, excerpts, structured labs and ranked IDs. The current note
is explicit input, never its own historical context. All eligible history is kept
for the small prototype, so ranking cannot hide a later negation. There is no vector
search or external retrieval service yet.

`StructuredFinding` has type, status, description, nonempty `EvidenceReference[]`,
optional uncertainty and source numeric value/unit. `ExtractionResult` adds missing
information. The default `structured-source-demo-v1` extractor copies the latest
explicitly coded symptom/lab per type/code and its source state/quote. Completed
prior labs are historical measurements; planned/unknown states remain uncertain.
It reports that free-text extraction is unavailable and never infers a diagnosis
or lab threshold. No LLM or numerical trend calculation is implemented.

The orchestrator rechecks retrieved records against PostgreSQL, validates evidence
ownership and time scope, verifies quotes and offset bounds, and matches numeric
facts to source values/units. Trigger rule IDs must match the loaded definitions;
supporting IDs must come from validated findings. Stage adapters and FastAPI
dependency overrides make execution testable without external API credentials.

## Demonstration rules

Enabled `trigger_rules` use this typed JSONB shape:

```json
{
  "demonstration": true,
  "lahde": "SYNTHETIC_FIXTURE_NOT_CLINICAL_GUIDANCE",
  "lahde_kohta": "demo-v1",
  "expression": {
    "kind": "group", "operator": "ALL",
    "conditions": [
      {"kind": "finding", "finding_type": "DEMO-CODE", "statuses": ["current"]}
    ]
  }
}
```

Groups support nested ALL/ANY (nonempty; depth capped at 12). Leaves match exact
finding types. Eligible statuses are `current` (default) or explicitly `historical`;
negated, resolved, uncertain, or explicitly ambiguous findings cannot trigger.
Optional `numeric` accepts `operator` (`lt/lte/gt/gte/eq`), Decimal `value`, and exact
`unit`. All comparisons execute in Python with no inferred thresholds/conversions.
ALL requires every child; ANY preserves evidence from matching children only.
Unsupported formats fail explicitly. Rule metadata is snapshotted for stable GETs.

The rule developer deliberately supplies sourced, labeled demo rules. The existing
seed has none enabled, so default analyses report that rules are missing rather than
inventing risk results. This task does not create or alter `rules.csv`; a future
team-authored engine plugs into `evaluate` through an explicit mapping.

## Future ML and additive storage migration

A source-grounded LLM/deterministic producer may implement `FindingExtractor` with
a stable versioned `name`. Future ML predictions use the separately typed internal
`ModelPrediction` (patient, model/version, as-of time, payload, evidence and uncertainty).
They are not accepted as established findings or automatically fed to rules. No
model, training, prediction persistence, public ML endpoint, or simulation is added.
Future prediction storage needs its own agreed schema rather than reusing original
observations or silently promoting predictions to clinical facts.

Migration `0002` adds only `analysis_runs.details` JSONB (default `{}`) and nullable
`clinical_findings.uncertainty`. The blocking gap was persistence of input/cutoff,
adapter versions, warnings/errors and uncertainty for stable saved responses. It
preserves existing columns/relationships. API startup never migrates automatically.

From `backend/` with `.venv` active: `python -m alembic upgrade head`, then
`RUN_DATABASE_TESTS=1 python -m pytest`. Tests use disposable PostgreSQL databases
and no live Verda/OpenAI keys. See README for startup commands.
