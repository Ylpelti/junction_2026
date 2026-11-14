# Independent patient-history retrieval

This module retrieves original synthetic patient records. It does not extract
clinical findings, assess risk/urgency, evaluate rules, call an LLM, or make referral
decisions. The existing API's demo `retrieval.py`, `context.py` and `extraction.py`
are preserved. The new engine is opt-in for the downstream developer.

## Integration boundary

```python
from app.rag.engine import RetrievalEngine, RetrievalOptions
from app.rag.repository import PatientRepository

repository = PatientRepository(db_session)
retrieve_context = RetrievalEngine(repository, options=RetrievalOptions(mode="auto"))
context = retrieve_context(scope=patient_scope, query=current_note.text)
numerical_history = repository.structured(scope=patient_scope, codes=None)
```

`context` is the unchanged shared `contracts.clinical_context.RetrievedContext`.
`scope` is `PatientScope`: patient UUID, exclusive event-time `as_of`, exclusive
`recorded_before` (default `as_of`), and optional inclusive `observed_since`.
Use the current note's event time as `as_of`; the note is explicit input and never
retrieved as its own history. Source observations retain original IDs, timestamps,
text, numerical values, units, and statuses. Results are chronological.

Numerical history is independently queried in SQL, including pending lab reports,
without ranking, embeddings, or a top-k limit. Its shared `StructuredPatientContext`
declares complete coverage for the requested scope/code filter. No mathematics runs.

`engine.search(...)` additionally returns RAG-local `RetrievalOutput.diagnostics`:
per-observation lexical, semantic and fused scores; primary ranking; timeline
expansion reasons; best matching chunk offsets; profile; missing/stale embeddings;
and serialized-source character count. Shared contracts have not been changed.

## Architecture and tradeoffs

- **Auto / complete baseline:** return all eligible history if it fits
  `max_source_chars` (default 32,000). Otherwise auto selects lexical, or hybrid
  when an explicit embedder was supplied. Explicit complete mode fails rather than
  silently truncating. This is the preferred baseline for our small histories.
- **Lexical:** PostgreSQL `ts_rank_cd` across Finnish stemming and the `simple`
  dictionary, plus an exact numeric-value match bonus. Bound query values are
  reduced to at most 64 unique alphanumeric terms joined by OR, so long notes do not
  require every word to appear. Codes, values and units are searchable. This is
  PostgreSQL full-text ranking, **not BM25**. Finnish morphology helps; abbreviations,
  synonyms and cross-language meaning remain limitations. No search service is added.
- **Dense:** optional local `intfloat/multilingual-e5-small`, pinned to commit
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`, with normalized 384-dimensional
  vectors and the required `query:`/`passage:` prefixes. The model is multilingual,
  including Finnish benchmark coverage, but is not clinically validated. The small
  model is practical on this CPU; no inference API receives patient text.
- **Hybrid:** reciprocal rank fusion with constant 60 combines lexical and dense
  ranks without pretending their score scales are equivalent. Scores are retrieval
  relevance, never cancer probabilities. Dense mode needs an explicit adapter and
  indexing; missing/stale vectors are reported, never replaced with fake vectors.
- **Patient-scoped exact vector search:** SQL filters patient and both time axes
  before ranking chunk vectors for the chosen profile. No ANN index is added for
  these small histories, avoiding filtered-ANN recall losses and index overhead.
- **Timeline expansion:** primary matches bring all same-code history, same-encounter
  records, next/latest clinical contacts, and later investigations/explicit
  negated/resolved/uncertain states. This is a conservative chronological heuristic,
  not a claim that records are clinically related. An old match and its expansion
  group fit atomically or are omitted with a missing-information message. Selective
  results declare partial coverage; consumers must not treat them as all history.

The budget is the sum of serialized original-source character counts, not an LLM
token guarantee. Observations are never rewritten/truncated to fit. A very long
observation that cannot fit is omitted with its group; increasing the budget or
agreeing a shared excerpt-window contract is required to send only part of it.

## Embedding workflow and storage

Migration `rag_0001` creates only `rag_embedding_chunks`. It does not alter shared
tables or models. The existing `observation_embeddings` table has fixed 1536-dimensional
vectors and no source fingerprint/chunk offsets. The RAG-owned table provides
384-dimensional vectors, source UUID FK, exact character spans, profile/revision,
source SHA-256 and creation time without misusing shared columns or padding vectors.
Deleting a source cascades only to its derived cache rows.

Short observations stay whole. Long observations use source-preserving overlapping
spans tested against the real tokenizer's 512-token ceiling, including metadata
and passage prefix. No document tail is silently discarded. Numeric-only records
use their original code/value/unit header. Long queries are encoded in bounded
segments and their normalized vectors averaged, rather than silently truncated.

Indexing locks source rows in UUID order, checks content/metadata fingerprints and
chunk layout, reuses current embeddings, and replaces stale chunks atomically in
a savepoint. Caller owns commit/rollback. A changed text/value/unit/status/time or
profile causes reindexing. Profiles coexist; vectors from different models are
never mixed. Retrieval checks freshness against the current source snapshot and
never writes cache rows automatically. `--force` explicitly recomputes a profile.

RAG cache metadata is isolated in `rag.storage.RagBase`; central shared-model
autogeneration is unchanged. The migration is explicit; dedicated tests inspect
its vector dimension/FK and upgrade/downgrade through the existing test fixture.
Alembic's central `check` alone does not inspect this separate RAG metadata.
Coordinate future migration branches with the other developer if both add heads.

## Local commands

From `cancersignal/backend/` with `.venv` active and PostgreSQL running:

```sh
python -m alembic upgrade head
# Existing synthetic seed, if not already loaded:
python -m app.db.seed

# No embedding dependencies or model downloads are needed for these:
python -m app.rag.cli query --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec \
  --as-of 2026-01-01T00:00:00Z --query "fatigue follow-up" --mode auto
python -m app.rag.cli structured --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec \
  --as-of 2026-01-01T00:00:00Z

# Optional local dense embeddings; downloads weights only with --download:
python -m pip install -r app/rag/requirements-local.txt
python -m app.rag.cli index --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec --download
python -m app.rag.cli query --patient-id dfbd029a-17bf-5cbf-8a38-2960061dceec \
  --as-of 2026-01-01T00:00:00Z --query "väsymys ja aiemmat tutkimukset" --mode hybrid
```

Use `--note-id UUID` instead of `--as-of` to load an existing clinical note owned by
the patient; its text supplies the query unless `--query` is explicit. `--top-k`
limits primary matches, not added timeline context. `--max-source-chars` bounds the
source payload. Model cache defaults to `.venv/rag-model-cache` (ignored by Git).
Later calls use local files only; configure `--model-cache`/`--revision` explicitly
for another pinned profile. No LLM credentials are needed.

## Independent tests and benchmark

```sh
python -m pytest tests/rag/test_engine.py tests/rag/test_independence.py
RUN_DATABASE_TESTS=1 python -m pytest tests/rag
python -m app.rag.cli benchmark --output /tmp/rag-lexical.json
python -m app.rag.cli benchmark --dense --output /tmp/rag-all.json
```

The benchmark reuses all eight seeded patients, adds five small Finnish/distractor
records in its transaction, and rolls back fixtures and benchmark embeddings.
`evaluation/labels.json` is separate from visible `records.json`; no general dataset
importer exists or is introduced. Labels are manually authored demonstration cases,
not clinical ground truth or a held-out performance claim. Dense/hybrid are marked
`not_run` when no embedder was requested. Tests use a clearly labeled fake adapter
for deterministic mechanics; the saved `evaluation/example-report.json` uses the
real pinned local model.

Reports compare recall/precision@K on primary ranks, missing required evidence in
the expanded context, follow-up preservation, latency, patient isolation, source
characters, and a clearly labeled token estimate. Complete baseline @K uses
chronological order; its full context is the meaningful recall baseline. Timings
exclude model load/indexing, which is separately reported. These five synthetic
scenarios cannot establish clinical retrieval quality or broad superiority.

## Shared interface proposals — not applied

The shared hit has one relevance score and the full original observation. Optional
matched-span references and multi-branch score metadata would help source highlighting
and bounded long-document contexts. For now those remain in RAG-local diagnostics;
no shared fields, downstream extraction, analysis services, rule engines, routes,
or frontend code are changed. The downstream owner can opt into this engine through
the existing shared callable protocol and decide persistence/prompt assembly.

Primary references: [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small),
[PostgreSQL full-text ranking](https://www.postgresql.org/docs/16/textsearch-controls.html),
[pgvector exact search](https://github.com/pgvector/pgvector).
