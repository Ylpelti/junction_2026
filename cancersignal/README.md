# CancerSignal — application guide

CancerSignal helps nurses identify overlooked colorectal cancer signals in synthetic patient histories and submit evidence-backed findings for physician review. Built for **Junction 2026 · AstraZeneca’s Equitable and Effective Cancer Care in Finland challenge**.

See the [project overview](../README.md) for the workflow, architecture, and repository map.

## Prerequisites

- Node.js 22+ and npm.
- Python 3.11+ with pip and `venv`.
- Docker with the Compose plugin and a running Docker daemon.

The frontend and backend run locally in separate terminals. Docker Compose runs PostgreSQL 16 with pgvector. The default structured-data demo needs no external AI service or API key.

## 1. Start PostgreSQL

From `cancersignal/`:

```sh
[ -f .env ] || cp .env.example .env
# Edit .env and choose a local POSTGRES_PASSWORD.
docker compose up -d --wait db
```

Both Compose and the backend use the `POSTGRES_*` settings in this file. The backend loads it regardless of its working directory; exported environment variables take precedence. Keep `.env` private and out of version control.

## 2. Start the backend

From `cancersignal/`:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m app.db.check
python -m alembic upgrade head
python -m app.db.seed
python -m uvicorn app.main:app --reload
```

On Windows, create the environment with `py -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1` in PowerShell.

The seed loads reproducible synthetic patients and enabled colorectal rules. Schema creation happens through Alembic, not API startup.

- API documentation: http://localhost:8000/docs
- Patient API: http://localhost:8000/api/v1/patients
- Liveness: http://localhost:8000/health

```sh
curl --fail http://localhost:8000/health
```

Expected response: `{"status":"ok"}`. This endpoint checks process liveness only; `python -m app.db.check` checks database connectivity and the vector extension. The API root `/` has no route.

## 3. Start the frontend

In a separate terminal, from `cancersignal/`:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. Select a synthetic patient, inspect the history, save a note for analysis, and review findings and source evidence before sending a physician-review request.

**Default extraction is structured-only.** It evaluates existing structured observations and derived laboratory findings; it does not understand arbitrary clinical prose. Enable optional LLM extraction to demonstrate that path.

## Configuration

Backend settings belong in `cancersignal/.env`. Restart the API after changes.

| Setting | Default | Purpose |
| --- | --- | --- |
| `POSTGRES_HOST` | `localhost` | Database host for the local Python process |
| `POSTGRES_PORT` | `5432` | Database port; also used by Compose |
| `POSTGRES_DB` / `POSTGRES_USER` | `cancersignal` | Database name and user |
| `POSTGRES_PASSWORD` | Required | Set your local database password |
| `CORS_ORIGINS` | Localhost and 127.0.0.1 on port 3000 | Allowed frontend origins, as a JSON array |
| `CANCERSIGNAL_RETRIEVAL` | `auto` | Complete history while it fits, otherwise lexical retrieval |
| `CANCERSIGNAL_EXTRACTION` | `off` | Structured-only extraction; `llm` enables clinical-text extraction |
| `CANCERSIGNAL_EXPLANATION` | `deterministic` | Finnish summaries; `llm` enables optional provider wording |
| `CANCERSIGNAL_EXTRACTION_ALLOW_LIVE` | `false` | Explicit opt-in to live extraction calls |
| `CANCERSIGNAL_EXPLANATION_ALLOW_LIVE` | `false` | Explicit opt-in to live explanation calls |

For a different backend origin, create `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Use the origin without `/api/v1`. Restart or rebuild the frontend after changing it. For a different frontend port, add its exact origin to the backend configuration, for example:

```dotenv
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://localhost:3001"]
```

### Optional AI and retrieval features

- **LLM extraction:** Configure the provider, model, credentials, and cache using the [extraction guide](backend/app/extraction/README.md). Cached responses can run without live calls; new live requests require explicit opt-in.
- **Hybrid retrieval:** Install the optional local embedding dependencies and prepare the model cache using the [retrieval integration guide](docs/rag-analysis-integration.md). The API does not download model weights during requests.
- **LLM explanations:** Follow the [explanation guide](backend/app/explanation/README.md) for separate provider settings. Deterministic Finnish explanations remain the default.

Retrieval always isolates patient history and enforces observation and recording cutoffs. Laboratory history is retrieved separately from narrative top-k results. Evidence is validated before persistence; Python rules determine alerts, and QCancer predictions remain separate.

## Development checks

From `backend/`, with the virtual environment activated:

```sh
python -m pytest
python -m pip check
```

With PostgreSQL running and migrations applied:

```sh
python -m app.db.check
python -m alembic check
# Opt-in integration tests create and remove their own test databases.
RUN_DATABASE_TESTS=1 python -m pytest
```

The integration suite needs a database role with `CREATEDB` permission. Database tests and external inference tests skip unless explicitly enabled; ordinary tests do not opt in to live provider calls.

From `frontend/`:

```sh
npm run typecheck
npm run build
```

If a restricted environment prevents Turbopack from opening its build-worker port, use `npm run build -- --webpack`. Run `npm start` to serve the completed production build; stop the development server first if it occupies port 3000. Run `npx playwright install chromium` once, then `npm test` for API/mapping and mocked browser workflow tests. See the [frontend integration guide](docs/final-frontend-integration.md) for real end-to-end testing.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Database port is occupied | Change `POSTGRES_PORT` in `.env`, then restart Compose and the backend. |
| Database authentication fails | `.env` must match the credentials used when the database volume was initialized. Editing the file does not change an existing database password. |
| Patient list is empty | Apply migrations and run `python -m app.db.seed` against the same database as the API. |
| Frontend cannot reach the API | Check `NEXT_PUBLIC_API_URL`, the running backend, and exact `CORS_ORIGINS`. |
| New prose does not yield findings | Default extraction is structured-only; consult the optional LLM setup. |
| QCancer returns `insufficient_data` | Required predictors are unknown. Missing inputs are deliberately not filled with invented values. |

Manage the database from `cancersignal/`:

```sh
docker compose ps
docker compose stop db
docker compose up -d --wait db
```

Data persists in the `postgres_data` volume. Do not remove it as a routine troubleshooting step. If an existing database lacks pgvector, enable it without deleting data:

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"'
```

## Further reading

- [Public API contracts](docs/contracts.md) and [data model](docs/data-model.md)
- [Shared pipeline contracts and evidence validation](backend/app/contracts/README.md)
- [Colorectal rulebook](docs/rulebook-colorectal.md)
- [QCancer model, assumptions, and licensing](docs/risk-models.md)
- [Physician-review API](docs/physician-review-api.md)
- [End-to-end integration notes](docs/end-to-end-integration.md)
- [Engineering guidance](AGENTS.md)

## Prototype limitations

Use **synthetic patient data only**. Authentication, EHR integration, and Finnish clinical validation are not implemented. Review requests, dismissal reasons, and physician decisions persist through the API. Actions use demo actors and simulate clinical workflow decisions; they do not book investigations or issue real referrals.

QCancer uses a synthetic Townsend placeholder of zero and is not calibrated for Finland. Numerical predictions do not control review alerts. “No signals identified” is not a negative cancer diagnosis. Failed or incomplete analysis provides no clinical conclusion. Clinicians retain responsibility for investigations and referrals.
