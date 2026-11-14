# Standardized storage contract

This is a synthetic-data prototype contract, not a clinical risk model. The public
API and replaceable demonstration pipeline are described in [contracts.md](contracts.md).
Embedding generation, LLM integration, and ML remain unimplemented. This document
describes storage; Pydantic schemas define the public API contract separately.

## Tables

| Table | Purpose and links |
| --- | --- |
| `patients` | Synthetic identity, birth date and sex. |
| `encounters` | A patient's dated contacts, type and optional organization. |
| `observations` | Original source notes, symptoms, labs and investigation reports; belongs to a patient and optionally their encounter. |
| `observation_embeddings` | Nullable `vector(1536)`, model identifier and timestamp, linked to one source observation. Unique per observation/model. |
| `trigger_rules` | Patient-independent, versioned rule definitions stored as JSONB. Unique name/version; disabled by default. |
| `analysis_runs` | Patient-specific run metadata, status, and provenance/warnings in `details` JSONB; does not modify source records. |
| `clinical_findings` | Generated findings linked to their run, optional uncertainty, separate from original observations. |
| `finding_evidence` | Finding/observation links, optional verbatim excerpt and character offsets. |
| `trigger_results` | One result per run/rule, with explicit boolean outcome and clinician-review flag. |
| `trigger_result_evidence` | Result/observation links supporting traceability. |

Entity primary keys are UUIDs. Create schemas generate UUIDv4 by default and accept
explicit UUIDs for imported records; the seed uses deterministic UUIDv5. Preserve
observation IDs across ingestion, embeddings and downstream outputs. Join-table
primary keys are `(finding_id, observation_id)` and `(trigger_result_id, observation_id)`.
All foreign keys are enforced; deletes do not cascade. Parent records must exist
before referencing rows are inserted.

`clinical_findings` and both evidence tables carry an additional `patient_id`.
Composite foreign keys enforce that encounters, analysis runs, results, and their
supporting observations belong to the same patient. Supplying another patient's
scope or later changing a linked parent's patient cannot bypass these constraints.
This duplication provides database enforcement without validation triggers.

SQLAlchemy models are in `backend/app/models/records.py`; relationships are
read-only navigation (`viewonly=True`). Write explicit foreign-key fields and
flush parents before inserting children. Create/read schemas are in
`backend/app/schemas/records.py`; use `Create.model_dump()` for ORM construction
and `Read.model_validate(record)` for serialization. Public response schemas extend
these records with evidence and saved provenance; see `schemas/analysis.py`.

## Source observations and statuses

- Types: `clinical_note`, `symptom`, `laboratory`, `investigation`, `vital_sign`,
  `diagnosis`, `medication`.
- Optional source status: `current`, `historical`, `resolved`, `negated`,
  `uncertain`, `completed`, `planned`. Null means no source status was supplied.
- Findings: `current`, `historical`, `resolved`, `negated`, `uncertain`.
- Runs: `pending`, `running`, `completed`, `failed`.
- Sex: `female`, `male`, `intersex`, `unknown`.

An observation requires nonblank source text or a numeric measurement (both may
coexist). `numeric_value` is `numeric(18,6)`/Python `Decimal`; retain original units
and code, and avoid silently converting source measurements. Codes remain strings;
no terminology catalogue is imposed. Preserve original note/report text, including
negations and uncertainty. Source status is not an AI risk classification. Treat
source records as append-only by convention; the schema does not prohibit edits.
No source status or finding means “no cancer.”

Rule `conditions` must be a JSON object with nonblank string `lahde` and
`lahde_kohta` source references, preserving the project rule-provenance requirement.
The demonstration engine's condition format is documented in `contracts.md`. This
table does not replace the planned `rules.csv` engine; integration requires explicit
mapping. No clinical rules are invented by the seed.

## Time and evidence

Timestamps use PostgreSQL `timestamptz`. Supply timezone-aware datetimes; Pydantic
rejects naive input and normalizes timestamps to UTC. SQLAlchemy sessions use UTC.
`birth_date` is a date. `observed_at` is when the source event occurred;
`recorded_at` is when it entered the record and may be later. Source imports should
supply both; the database defaults `recorded_at` to insertion time if omitted.
The remaining `created_at` fields default to database insertion time.

Future history consumers must filter **patient ID first**, then require
`observed_at < t` and `recorded_at < t` before ranking. Use the note's timestamp as
the cutoff; never include the current note as its own historical evidence. Indexes
cover patient/time filters. Clinical/event time and recording time remain distinct.
The retrieval component and database tests enforce this cutoff.

Evidence must reference actual observation UUIDs. Offsets are zero-based Unicode
character indexes, with an exclusive end: `observation.text[start_offset:end_offset]`.
Both offsets must be null or form a nonempty range with an excerpt. Numeric evidence
can reference an observation without an excerpt. The analysis service verifies that an
excerpt matches original text and offsets fit the text; the database enforces range
shape and patient ownership, not verbatim text matching. Explanations must
only cite persisted observation and rule IDs.

## RAG and ML consumption

The embedding dimension is **1536**, a storage choice, not a selected provider/model.
`embedding_model` identifies the exact model/version; do not compare vectors from
different models. Null vectors are pending and must be excluded from future search.
Changing dimension requires a migration and explicit model agreement. No vector
index or embedding generation is added yet.

Use original observations as input and retain their UUIDs as provenance; derived
findings/results stay in their separate tables. Group evaluation splits by patient
and respect time cutoffs. Synthetic patterns and measurements are fixtures, not
validated thresholds or human-labelled ground truth. Do not use them to claim
clinical performance.

## Setup and fixtures

From `cancersignal/`, start PostgreSQL with `docker compose up -d --wait db`.
Then, from `backend/` with `.venv` activated:

```sh
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m alembic check
python -m app.db.seed
python -m pytest
RUN_DATABASE_TESTS=1 python -m pytest
```

The initial migration enables pgvector and creates all ten tables. It never calls
`create_all` at API startup. Autogeneration preserves unrelated existing tables.
Downgrades drop application tables and their data; use them only intentionally.
The vector extension is retained because other tables may depend on it.

The seed inserts 8 explicitly fictional patients, 32 encounters, 98 observations
from 2020–2026, and 8 null embedding placeholders (`pending-1536`). It includes
repeated symptoms, denials, resolutions, normal visits, completed investigations,
and uncertain/missing follow-up in source notes. It creates no findings, rule
definitions, analysis runs, or trigger results. Reruns insert only missing stable
IDs and never overwrite existing rows. It uses no randomness or external services.

Database tests opt in with `RUN_DATABASE_TESTS=1`. They use configured PostgreSQL
credentials to create a uniquely named disposable database, verify migration
upgrade/downgrade/upgrade, run integrity tests in rolled-back transactions, and
drop only that disposable database. The local role needs `CREATEDB` permission;
the provided Compose role has it. The development database is not reset by tests.
