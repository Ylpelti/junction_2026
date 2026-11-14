# CancerSignal

AstraZeneca Cancer Care Challenge · Junction 2026

CancerSignal is a planned AI-assisted tool for nurses and healthcare professionals.
It will combine new clinical notes with relevant patient history through
patient-specific retrieval-augmented generation (RAG), highlighting possible
cancer-related risk signals with references to original records for physician review.

This repository currently contains **only a framework scaffold**: a Next.js
placeholder page, a FastAPI health endpoint, and a PostgreSQL/pgvector backend
foundation. Patient workflows, AI/RAG, datasets, ML, and simulations are not
implemented. There are no patient tables or domain schemas yet.

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
│   │   └── main.py
│   ├── tests/      # API smoke test, no database required
│   ├── pyproject.toml
│   └── requirements.txt # Compatibility entry point for runtime installation
├── simulation/     # Reserved for future work; no implementation
├── data/           # Reserved for synthetic data
└── docs/           # Reserved for shared documentation
```

The frontend and backend run independently in two terminals. PostgreSQL runs in
Docker; Python runs locally. No external service or API key is required.
Models, domain schemas, and AI packages will be added only when their first
feature is implemented.

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

Checks and production build (from `frontend/`):

```sh
npm run typecheck
npm run build
npm start
```

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
python -m uvicorn app.main:app --reload
```

On Windows, use `py -m venv .venv` and activate with
`.venv\Scripts\Activate.ps1` in PowerShell instead.

- API: <http://localhost:8000>
- Interactive API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

Verify the running backend:

```sh
curl --fail http://localhost:8000/health
```

Expected response: `{"status":"ok"}`. This is a liveness endpoint; it does not
check database readiness. The API and its test can run without PostgreSQL or `.env`.
The API root has no route yet; use `/docs` or `/health`. The frontend does not call
the backend yet; integration will be added with the first feature.

Checks (from `backend/`, with the virtual environment activated):

```sh
python -m pytest
python -m pip check
python -m app.db.check
```

The database check executes `SELECT 1` through SQLAlchemy and confirms that the
`vector` extension is enabled. It requires the Compose database and `.env` and
exits nonzero on failure. The pytest API test requires neither. There is no Python
build step. To run without automatic reload, use `python -m uvicorn app.main:app`.
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
routes; callers explicitly commit writes. No tables are created automatically.

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
