# CancerSignal

AstraZeneca Cancer Care Challenge · Junction 2026

CancerSignal is a planned AI-assisted tool for nurses and healthcare professionals.
It will combine new clinical notes with relevant patient history through
patient-specific retrieval-augmented generation (RAG), highlighting possible
cancer-related risk signals with references to original records for physician review.

This repository currently contains a Next.js nurse dashboard and physician queue,
a FastAPI API, a PostgreSQL/pgvector backend foundation, relational patient/evidence
models, a small synthetic seed dataset, and database-backed patient and analysis
APIs. The internal pipeline has baseline history retrieval, a structured-source
demo extractor, and sourced demonstration rules. LLM/free-text extraction,
ML and simulations are not implemented. The independent [RAG engine](backend/app/rag/README.md)
also supports optional local dense/hybrid retrieval; the API still uses its demo
retriever until downstream integration. See [the API contract](docs/contracts.md)
and [the data model](docs/data-model.md).

Independent RAG, extraction and mathematical components can use the
[shared pipeline contracts](backend/app/contracts/README.md), including pure
evidence validation and synthetic JSON examples. These handoffs do not change API v1.

## Structure

```text
cancersignal/
├── AGENTS.md       # Project context and development principles
├── README.md
├── .gitignore
├── .env.example    # Local database settings (copy to .env)
├── docker-compose.yml # PostgreSQL 16 with pgvector
├── frontend/       # Next.js App Router + TypeScript
├── backend/
│   ├── app/
│   │   ├── api/    # HTTP routes (health only)
│   │   ├── core/   # Environment-based settings
│   │   ├── db/     # SQLAlchemy sessions, connectivity check, extension init
│   │   ├── models/ # Relational records and enums
│   │   ├── schemas/ # Pydantic create/read contracts
│   │   ├── services/ # Database-backed use cases and analysis orchestration
│   │   ├── rag/    # Internal retrieval and replaceable extraction
│   │   ├── reasoning/ # Demonstration rule engine and Python interfaces
│   │   └── main.py
│   ├── alembic/    # Versioned schema migrations
│   ├── tests/      # API, schema, and opt-in PostgreSQL tests
│   ├── pyproject.toml
│   └── requirements.txt # Compatibility entry point for runtime installation
├── simulation/     # Reserved for future work; no implementation
├── data/           # Reserved for synthetic data
└── docs/           # Reserved for shared documentation
```

The frontend and backend run independently in two terminals. PostgreSQL runs in
Docker; Python runs locally. No external service or API key is required.
No external LLM provider is configured. Existing fixtures contain no enabled rules;
analysis responses explicitly report unavailable extraction and missing rules.

## Prerequisites

- Node.js 22 LTS or newer and npm.
- Python 3.11 or newer with `venv` and pip.
- Docker with the Compose plugin, with the Docker daemon running (for the database).

Run the commands below from `cancersignal/` inside the repository.

## Frontend

```sh
cd frontend
npm ci
npm run dev
```

Open <http://localhost:3000>. Edit `frontend/app/page.tsx` to begin development.

The frontend calls `http://localhost:8000` by default. To use a different backend,
set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to its origin (without `/api/v1`),
then restart/rebuild Next.js. Appointments and physician workflow currently use
documented local/demo fallbacks; see [backend-todo.md](docs/backend-todo.md).

Checks and production build (from `frontend/`):

```sh
npm run typecheck
npm run build
npm start
```

If a restricted environment prevents Turbopack from opening its build-worker port,
use `npm run build -- --webpack` to produce the production build.

`npm start` serves the completed production build on port 3000. Stop the development
server before starting it on the same port. No frontend tests are configured yet.

## Backend

From `cancersignal/`, initialize the local database configuration:

```sh
cp .env.example .env
# Edit .env and choose a local POSTGRES_PASSWORD before starting PostgreSQL.
docker compose up -d --wait db
```

Keep `.env` private; it is ignored by Git. The example password is a development
placeholder. Settings automatically read `cancersignal/.env` regardless of the
Python process's working directory; exported environment variables take precedence.
Python and Compose use the same `POSTGRES_*` settings. `POSTGRES_HOST=localhost`
is for the locally running backend, and the database port binds only to localhost.
If port 5432 is already occupied, change `POSTGRES_PORT` in `.env` before startup.

Install the backend and development tools:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m app.db.check
python -m alembic upgrade head
# Optional: load the small, reproducible SYNTHETIC dataset.
python -m app.db.seed
python -m uvicorn app.main:app --reload
```

On Windows, use `py -m venv .venv` and activate with
`.venv\Scripts\Activate.ps1` in PowerShell instead.

### Frontend origins / CORS

FastAPI allows `http://localhost:3000` and `http://127.0.0.1:3000` by default.
To use another frontend port or hosted URL, set `CORS_ORIGINS` as a JSON array in
`cancersignal/.env` (or an exported environment variable), then restart FastAPI:

```dotenv
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://localhost:3001","https://your-frontend.example"]
```

Use exact origins: scheme, hostname and optional port, with no path or wildcard.
An empty array disables cross-origin access. GET and POST are enabled, including
JSON POST preflight requests; cookies/credentials are disabled. CORS configuration
does not require database credentials, so `/health` remains independently runnable.
`NEXT_PUBLIC_API_URL` identifies the backend; `CORS_ORIGINS` lists allowed frontend
origins. Neither setting adds `/api/v1` or changes the existing endpoint contracts.

- API: <http://localhost:8000>
- Interactive API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

Verify the running backend:

```sh
curl --fail http://localhost:8000/health
```

Expected response: `{"status":"ok"}`. This is a liveness endpoint; it does not
check database readiness. The API and its test can run without PostgreSQL or `.env`.
The API root has no route; use `/docs`, `/health`, or `/api/v1/patients`. Public
patient, observation, timeline, and analysis endpoints use the `/api/v1` prefix.
Analysis accepts either an existing note UUID or a new `ObservationCreate` note;
see [docs/contracts.md](docs/contracts.md) for payloads, filtering, and adapter interfaces.
The frontend has not been changed in this task.

Checks (from `backend/`, with the virtual environment activated):

```sh
python -m pytest
python -m pip check
python -m app.db.check
python -m alembic check
# Optional PostgreSQL integrity suite; creates and removes its own test database.
RUN_DATABASE_TESTS=1 python -m pytest
```

The database check executes `SELECT 1` through SQLAlchemy and confirms that the
`vector` extension is enabled. It requires the Compose database and `.env` and
exits nonzero on failure. API/schema tests require neither; database tests skip
unless opted in and need the Compose database role's CREATEDB permission. There is
no Python build step. To run without automatic reload, use `python -m uvicorn app.main:app`.
The existing `python -m pip install -r requirements.txt` command still installs
runtime dependencies; development tools require the `[dev]` extra above.

Database lifecycle commands (from `cancersignal/`):

```sh
docker compose ps
docker compose stop db
docker compose up -d --wait db
```

Database files persist in the named `postgres_data` volume. Initialization enables
pgvector only when a new database volume is created. For an existing database
that lacks the extension, enable it without deleting data:

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"'
```

Changing database credentials in `.env` does not change credentials already stored
in an existing volume. Keep those settings consistent with the initialized database.
Avoid removing the volume unless you intend to delete its contents.

`app/api/` owns HTTP routes, `app/core/` owns settings, and `app/db/` owns database
connections. `get_session` provides a request-scoped SQLAlchemy session for future
routes; callers explicitly commit writes. Apply Alembic migrations to create tables;
API startup never creates them. See [docs/data-model.md](docs/data-model.md) for
schema conventions, evidence integrity, seed contents, and integration-test behavior.

## Planned work and ownership

1. **Frontend:** nurse dashboard, clinical notes, patient history, user experience.
2. **Backend & AI:** retrieval, LLM analysis, structured clinical data, risk signals.
3. **Data & Simulation:** synthetic datasets, optional scikit-learn/PyTorch
   experiments, evaluation, and before-and-after waiting-time simulations.

Agree shared API contracts and data schemas before implementing integrations.
Keep runtime dependencies local to each component; no monorepo task runner is needed.

## Prototype boundaries

Use **synthetic patient data only**. This is a hackathon prototype, not a production
clinical application. AI supports healthcare professionals and does not autonomously
diagnose cancer or make referral decisions. A physician reviews findings and any
referral. Simulated outcomes must not be presented as clinically validated results.

See [AGENTS.md](AGENTS.md) for the full project context and development principles.

Framework references: [Next.js setup](https://nextjs.org/docs/app/getting-started/installation)
and [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/).
