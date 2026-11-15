> Archived v1 guide. Use [README.en-v2.md](README.en-v2.md) for active English fixtures and insert-only seed behavior.

# Synthetic Finnish demonstration patients

See the [current integration verification](../../../../docs/demo-seed-integration.md)
for actual application-database and current-pipeline test results.

Four entirely fictional patients, 21 encounters and 41 source observations, fixed
at 2026-11-12. No personal identifiers, predictions or evaluation answers are
stored in the source records. Finnish notes include uncertainty and relevant
negative findings. These are demonstration scenarios, not clinical validation.

| Patient | Scenario | Stable patient UUID |
| --- | --- | --- |
| SYNTHETIC Laine | Repeated symptoms, Hb 142 → 134 → 124 → 113 g/L over six years | `138fff92-bea8-5f85-a95a-5fb502fd9e57` |
| SYNTHETIC Nieminen | Recurrent GI symptoms, planned colonoscopy, completion undocumented | `9f1864d7-0a2b-55d2-a007-7f886ab65b2e` |
| SYNTHETIC Heikkinen | Completed colonoscopy, subsequent symptom resolution, current shoulder complaint | `53bcac07-8145-5a0a-bcf9-a64720ceecac` |
| SYNTHETIC Korhonen | Routine care, stable Hb, relevant negatives | `6fa564bb-9001-5226-b01e-2fbb61cc4526` |

The existing frontend fallback characters have different ages, IDs and canned
results. These patients are independent API-backed records. No frontend code or
fallback predictions are changed or copied. Select API data to see these histories.

## Initialize and load

Run from this worktree's `cancersignal/`. Requires Python 3.11+, Docker Compose,
and a configured local PostgreSQL password. On a new installation only, copy
`.env.example` to `.env` and set the password; never overwrite an existing `.env`.
A worktree does not inherit ignored `.env` files or virtual environments.
Exported `POSTGRES_*` settings take precedence over `.env`.

```sh
docker compose up -d --wait db
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m app.db.check
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.db.demo validate
.venv/bin/python -m app.db.demo seed
.venv/bin/python -m app.db.demo list
```

`seed` creates only the four new patients and their source records. Repeating it
restores changed fixture fields and inserts missing records, without removing
additional notes/analyses. UUID collisions with a different patient marker or
owner fail closed. Baseline `python -m app.db.seed` remains unchanged and can
coexist (adds its eight patients and rules). To load rules without baseline patients:

```sh
.venv/bin/python -c 'from sqlalchemy.orm import Session; from app.db.session import get_engine; from app.db.seed_rules import seed_rules; s = Session(get_engine()); seed_rules(s); s.commit(); s.close()'
```

All source IDs use UUIDv5 with `NAMESPACE_URL` and
`https://cancersignal.invalid/demo/v1/{kind}/{key}`. Kinds are `patient`,
`encounter`, `observation`; keys are the slug, slug/date, and slug/date/type.
Keys and IDs are immutable within v1. Removing rows from a future fixture does
not delete them on ordinary seed; use the explicit reset to restore the canonical
set. Validation rejects unsupported fields, ambiguous lab units, invalid ownership,
nonfinite measurements and recording timestamps preceding measurements.
The complete load/reset is transactional, with a savepoint for programmatic
callers and a transaction-scoped advisory lock serializing demo commands.

## Laboratory mapping

`patients.json` records system `http://loinc.org`, code `718-7`, unit `g/L`.
[LOINC 718-7](https://loinc.org/718-7) identifies haemoglobin mass concentration
in blood and lists g/L among its example units (verified 2026-11-14).
The ingestion-only mapping in `app/db/demo.py` stores the application's existing
`B-Hb` alias. `B-Hb` here is not a claim about a Finnish national numeric code.
The code-system provenance stays in the version-controlled fixture because the
existing observation table has no code-system column. Values, units and both
timestamps are copied unchanged; g/dL inputs are rejected, not silently relabelled.
No migration, rule change or reference range is introduced. Both derived findings
and the QCancer Hb adapter already recognize this alias. Existing observations
outside these deterministic fixture IDs are never recoded.

Only Hb is included as a quantitative lab. Ferritin is deliberately absent:
falling Hb alone does not establish iron deficiency or cancer. Full QCancer inputs
(smoking/alcohol categories, BMI and sex-specific binary history) are not uniformly
known, so `insufficient_data` is a valid outcome. Neither missing facts nor the
separate evaluation fixture are used to force predictions.

## RAG indexing and analysis

Sequence: migrate → seed → index (for dense/hybrid) → analyze. The normal `auto`
retriever can retrieve these small histories completely without embeddings.
Finnish lexical retrieval also needs no embedding downloads.

```sh
.venv/bin/python -m app.rag.cli query \
  --patient-id 138fff92-bea8-5f85-a95a-5fb502fd9e57 \
  --as-of 2026-11-12T09:00:00Z --query 'väsymys ja hemoglobiinin kehitys' --mode complete
```

For local dense/hybrid mode, use the existing pinned E5 embedder and indexer:

```sh
.venv/bin/python -m pip install -r app/rag/requirements-local.txt
for patient in $(.venv/bin/python -c 'from app.db.demo import load_dataset; print(" ".join(str(p.id) for p in load_dataset().patients))'); do
  .venv/bin/python -m app.rag.cli index --patient-id "$patient" --download
done
.venv/bin/python -m app.rag.cli query \
  --patient-id 9f1864d7-0a2b-55d2-a007-7f886ab65b2e \
  --as-of 2026-11-12T09:00:00Z --query 'tähystyksen toteutuminen' --mode hybrid
```

`--download` explicitly permits model weight downloads; omit it after caching.
Use the same `--model-cache` for indexing and querying when overriding the default.
The existing indexer reuses unchanged chunks; updated sources invalidate **all**
profiles in both cache tables during seeding. Reindex after changing source data
or resetting. No fabricated vectors or pending embedding placeholders are seeded.
Mechanical integration tests use the existing deterministic fake embedder, not a
claim of real-model retrieval quality.

Start the API and inspect histories:

```sh
.venv/bin/python -m uvicorn app.main:app --reload
# In another terminal:
curl http://localhost:8000/api/v1/patients
curl http://localhost:8000/api/v1/patients/138fff92-bea8-5f85-a95a-5fb502fd9e57/observations
```

From `backend/`, analyze the latest Laine note through the existing API:

```sh
note_id=$(.venv/bin/python -c 'from app.db.demo import demo_id; print(demo_id("observation", "laine/2026-11-12/note"))')
curl -X POST http://localhost:8000/api/v1/patients/138fff92-bea8-5f85-a95a-5fb502fd9e57/analyses \
  -H 'Content-Type: application/json' -d "{\"note_observation_id\":\"$note_id\"}"
```

Current-note time is the exclusive history cutoff on both timestamp axes. Earlier
labs precede the latest notes so they can enter the analysis. Free-text symptom
interpretation requires the existing configured extraction adapter; default
structured-only extraction does not understand arbitrary Finnish prose. This seed
does not enable external calls or guarantee alerts. Follow the existing extraction
and RAG READMEs for cached/live LLM configuration.

## Explicit demo reset

Stop active demo requests before resetting. The command requires both an explicit
demo-environment opt-in and the exact connected database name. This is a local
operator guard, not authentication or production access control.

```sh
CANCERSIGNAL_DEMO_ENV=demo .venv/bin/python -m app.db.demo reset \
  --confirm-database cancersignal
```

Replace `cancersignal` only with the actual database intended for this demo.
Reset accepts no external manifest or arbitrary patient IDs. It checks the four
registered UUID/name/creation markers, removes **all** observations and encounters
for those patients (including notes added during demos), related analysis runs,
findings, evidence, trigger results, physician decisions, dismissals, physician review requests, and embeddings,
then restores the canonical sources atomically. It preserves the four identities,
all unrelated patients and their records, global rules and the database volume.
It is safe to repeat, including before initial seeding. No public reset endpoint.

Ordinary seed preserves historical analysis snapshots even if their source records
change; reset and rerun analysis for a clean demonstration. External extraction
caches and browser-only state are outside this database reset. No analysis or
risk-model logic has been modified.

## Tests and evaluation labels

```sh
.venv/bin/python -m pytest tests/test_demo.py
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest tests/test_demo.py tests/rag tests/test_api.py tests/test_reviews.py
```

Database tests use the existing fixture that creates/migrates/drops its own random
PostgreSQL test database; the configured role must have CREATEDB permission.
They cover repetition, updates, ownership/FKs, API reads, time order, mapped units,
RAG retrieval/cache reuse and invalidation, reset guards, dependent artifacts,
rollback and unrelated-record preservation.

`tests/fixtures/demo/labels.json` holds manually authored source references and
question expectations separately from clinical records. It is never seeded or
passed to RAG/LLMs. It is not held-out clinical ground truth and no A/B/C datasets
were modified.
