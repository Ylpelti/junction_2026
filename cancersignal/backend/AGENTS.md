# Backend instructions

Inherit `../AGENTS.md`. Paths below are relative to `backend/`.

## Boundaries

- `app/api/` handles HTTP, `app/schemas/` public payloads, `app/services/`
  orchestration, `app/models/` persistence, and `app/contracts/` shared handoffs.
- `app/services/analysis_service.py` validates retrieved context and extracted
  evidence, derives lab findings, evaluates rules, computes separate QCancer
  predictions and persists results. Preserve failed-run semantics and provenance.
- The API's baseline retrieval and the opt-in independent `app/rag/engine.py`
  are distinct. Read `app/rag/README.md` before integrating or changing retrieval.
- `app/extraction/` consumes supplied snapshots. The API adapter lives in
  `app/services/llm_extraction.py`; extraction must not query extra patient records
  or evaluate clinical rules. Read `app/extraction/README.md` for configuration.
- `app/db/seed_rules.py` defines sourced SUO rules; `app/reasoning/` evaluates
  them and derives lab findings. Numerical model code is in `app/risk_models/`.
  Preserve the QCancer disclaimer, AGPL license and missing-input behavior.
- Review requests persist nurse-to-physician handoffs. Do not imply physician
  decisions or dismissals are persisted until corresponding APIs exist.
- Apply schema changes through Alembic; application startup does not create
  tables. Coordinate migration heads. RAG cache metadata is separate from the
  central SQLAlchemy metadata; central `alembic check` does not cover it all.

## Setup and checks

With the Compose database configured and running from the project directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m app.db.check
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.db.seed
.venv/bin/python -m app.db.seed_demo   # demo patients from data/patients/demo_patients.json
.venv/bin/python -m uvicorn app.main:app --reload
```

Demo patients (Laine, Nieminen, Korhonen, Heikkinen) are versioned in
`data/patients/demo_patients.json`:
- **Lab codes:** LOINC 718-7 for haemoglobin and 2276-4 for ferritin. FIT uses the local code `F-HB-FIT`, because no verified LOINC code exists in ug/g.
- **Loading:** `app/db/seed_demo.py` validates the file (`--check` runs without a database) and inserts it with stable IDs. Existing rows are never changed.
- **Expected alerts:** each patient's expected alert without LLM extraction is in the file and is checked by `tests/test_seed_demo.py`.

The seed is insert-only, not a database reset. Environment settings read
`cancersignal/.env`; exported variables take precedence.

```sh
.venv/bin/python -m pytest
.venv/bin/python -m pip check
# Requires the configured PostgreSQL database:
.venv/bin/python -m alembic check
# Opt-in integration tests create/remove their own test database:
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest
```

The default suite includes API, contracts, schemas, evidence, rules, reviews,
extraction and retrieval checks. PostgreSQL tests skip unless opted in and require
CREATEDB permission. Run targeted tests while editing, then relevant wider checks.

## Optional services

`CANCERSIGNAL_EXTRACTION=off` is the default. To use the LLM adapter, select `llm`
and configure `EXTRACTION_MODEL`, `EXTRACTION_API_KEY` and provider settings through
exported variables or `CANCERSIGNAL_EXTRACTION_ENV_FILE`. Live calls additionally
require `CANCERSIGNAL_EXTRACTION_ALLOW_LIVE=true`; validated cache replay does not.
Use `CANCERSIGNAL_EXTRACTION_CACHE_DIR` for the API cache. Runtime LLM use needs
`pip install -e ".[llm]"` (the dev extra already includes httpx).

Dense RAG requires optional `app/rag/requirements-local.txt` dependencies and
explicit model download/indexing; ordinary tests and baseline API operation do not.
Configure `CORS_ORIGINS` as a JSON array of exact frontend origins. Health and CORS
settings remain usable without database credentials.
