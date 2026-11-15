# RAG in the analysis API

`POST /api/v1/patients/{patient_id}/analyses` now uses the existing
`app.rag.engine.RetrievalEngine` through `services.history_retrieval`. There is
one retrieval engine; the original full-history demo retriever remains selectable
for comparison. No new endpoints, public DTO fields, model predictors, clinical
rules, embedding tables or migrations were introduced.

## Configuration

Set these in `cancersignal/.env` or export them before starting FastAPI. Restart
the process after changing settings (the existing settings loader is cached).

| Variable | Default | Behavior |
| --- | --- | --- |
| `CANCERSIGNAL_RETRIEVAL` | `auto` | `auto`, `lexical`, `hybrid`, or `baseline` |
| `CANCERSIGNAL_RETRIEVAL_TOP_K` | `5` | Primary matches; timeline expansion may add more records |
| `CANCERSIGNAL_RETRIEVAL_MAX_SOURCE_CHARS` | `32000` | Budget for whole serialized narrative sources; not a token limit |
| `CANCERSIGNAL_RETRIEVAL_AUTO_INDEX` | `true` | In hybrid mode, refresh eligible new/changed observations before search |
| `CANCERSIGNAL_RETRIEVAL_MODEL_CACHE` | `<Python virtualenv>/rag-model-cache` | Cached pinned local E5 weights; no request-time downloads |

`auto` returns complete history when it fits, otherwise lexical retrieval.
`lexical` uses PostgreSQL English/simple full-text ranking and timeline expansion.
These API modes never load embedding dependencies. `hybrid` explicitly loads the
existing pinned `multilingual-e5-small` adapter and combines lexical/vector ranks.
`baseline` runs the original all-history lexical-overlap adapter without a budget.
Retrieval settings are independent of `CANCERSIGNAL_EXTRACTION=off|llm`.

## Data flow and safety boundaries

1. Both retrieval and structured access filter the patient UUID, event time
   `observed_at < note.observed_at`, and knowledge time
   `recorded_at < note.observed_at`. The current note is explicit extraction input.
2. The existing engine selects whole original observations and expands timeline
   groups, including same-code history, subsequent contacts, investigations and
   later negative/resolved/uncertain states. Groups fit atomically or are omitted
   with a warning, so a budget cannot publish half of a selected group. This is a
   conservative chronology heuristic, not clinical reconciliation.
3. The service bridge retains the engine's original shared `RetrievedContext`,
   including coverage, relevance and component provenance. The LLM adapter consumes
   it unchanged instead of labelling a selective result as complete. Original IDs,
   full text/excerpts, source timestamps, values, units and statuses are preserved.
4. Independently, `PatientRepository.structured(codes=None)` fetches **all** eligible
   laboratory/vital/numeric records, including pending lab reports, without ranking,
   top-k, pagination or the narrative budget. The orchestrator validates this branch
   against PostgreSQL before passing its complete history to existing lab logic.
   QCancer receives the union of validated source records. No model code changes.
5. Extracted findings and QCancer predictors are first checked against only the
   extraction snapshots and the input note. Python-derived lab findings may then
   cite the separate structured branch. Unknown predictors remain unknown;
   QCancer can still return `insufficient_data`. Predictions do not set rule urgency.

API v1 is unchanged. `provenance.context_observation_ids` now records the union of
retrieved narrative and complete structured history (excluding the input note).
`retrieval_method` identifies the effective engine mode and, when used, embedding
profile. Coverage gaps and lexical fallback are persisted in `missing_information`.
Scores/configuration digests remain internal to the rich retrieval context;
the standalone RAG CLI also exposes diagnostics. `source_observations` continues
to resolve the findings/trigger/prediction evidence actually cited in the response.
GET reads the saved run without reindexing or rerunning the pipeline.

## Indexing and failure behavior

API hybrid indexing reuses `index_patient(..., scope=...)`, restricted to that
patient and both cutoffs. It fingerprints originals, reuses current chunks and
atomically replaces changed text/value/unit/status/time/chunk metadata. Newly
saved observations and direct database corrections are refreshed on the **next
eligible hybrid analysis**, not in the observation POST request. The current input
note becomes eligible only for a later analysis. There is no update API, background
worker, or on-save embedding requirement.

Indexing and hybrid search share a savepoint within the analysis transaction. A
missing optional dependency, unavailable local weights, embedding failure, missing
cache table, or incomplete/stale cache rolls back this optional work and retries
lexical retrieval with `hybrid_unavailable_lexical_fallback` in missing information.
With automatic indexing disabled, preindex all eligible sources for the selected
profile; incomplete caches also trigger lexical fallback. A PostgreSQL outage is
still a database error, not a successful analysis. Failures in extraction/rules
retain the existing failed-run behavior. No patient/provider error text is exposed.

The independent CLI index command still indexes all observations of the specified
patient, regardless of analysis cutoff, and can repair the cache manually. Only
retrieval filters determine which originals can become analysis evidence. There
are no new migrations: existing `rag_0001` owns the cache table.

## Install and run

From `cancersignal/`, configure `.env` from `.env.example` if necessary, then:

```sh
docker compose up -d --wait db
cd backend
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m app.db.seed

# No embedding dependencies and no external LLM calls:
CANCERSIGNAL_RETRIEVAL=lexical CANCERSIGNAL_EXTRACTION=off \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use the actual configured PostgreSQL port; Compose and `POSTGRES_PORT` must match.
In a second terminal, analyze the existing synthetic patient/note:

```sh
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body -X POST \
  http://127.0.0.1:8000/api/v1/patients/dfbd029a-17bf-5cbf-8a38-2960061dceec/analyses \
  -H 'Content-Type: application/json' \
  -d '{"note_observation_id":"932f6e21-6ab3-5adf-a92c-8db06fa568d4"}'
```

Optional hybrid setup, from `cancersignal/backend/` with the same virtualenv active:

```sh
python -m pip install -r app/rag/requirements-local.txt
# Explicit initial download of the pinned local model; no LLM credentials needed.
python -m app.rag.cli index \
  --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec --download
# Idempotent refresh after later writes/corrections, using cached weights only:
python -m app.rag.cli index --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec
# Inspect retrieval and the independent full measurement history:
python -m app.rag.cli query \
  --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec \
  --note-id 932f6e21-6ab3-5adf-a92c-8db06fa568d4 --mode hybrid
python -m app.rag.cli structured \
  --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec \
  --note-id 932f6e21-6ab3-5adf-a92c-8db06fa568d4
# Stop the previous server before restarting on the same port:
CANCERSIGNAL_RETRIEVAL=hybrid CANCERSIGNAL_EXTRACTION=off \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For a custom cache directory, pass `--model-cache /absolute/path` to both CLI index
and query, and set `CANCERSIGNAL_RETRIEVAL_MODEL_CACHE=/absolute/path` for FastAPI.
The revision is pinned by the existing adapter, never chosen from patient text.

## Verification

```sh
# Offline configuration/bridge tests:
python -m pytest tests/rag/test_analysis_adapter.py tests/test_llm_extraction.py
# Disposable PostgreSQL database; configured role needs CREATEDB:
RUN_DATABASE_TESTS=1 CANCERSIGNAL_EXTRACTION=off \
  python -m pytest tests/rag/test_analysis_integration.py tests/rag/test_postgres.py tests/test_api.py
RUN_DATABASE_TESTS=1 CANCERSIGNAL_EXTRACTION=off python -m pytest
```

Integration tests reuse the existing seeded synthetic histories without editing
benchmark fixtures. They exercise real FastAPI routes, PostgreSQL full-text and
pgvector search, resolved/negated timelines, full falling/normalized Hb histories,
insert/reindex behavior, both temporal cutoffs, cross-patient isolation, grounded
offline LLM extraction, cache/provider failure rollback, stable saved responses,
and unchanged QCancer calculated/insufficient-data behavior. Dense mechanics use
the existing deterministic fake embedder; they do not validate clinical quality.
