# Render backend + Vercel frontend

Prepared from `origin/main` at `6290872`, on `infra/render-vercel-demo`.
Existing uncommitted deployment work was copied selectively into this isolated
branch; its source worktree was not edited. No clinical implementation or prompt
changes are included. No hosted service or database has been created or changed.

## Database

Set `DATABASE_URL` securely on the backend. PostgreSQL from a Vercel-connected
provider works too: the database must support the `vector` extension. This does
not require hosting the database on Render. Use the provider's direct connection
URL for migrations; use its recommended runtime URL for the API. Preserve TLS
query parameters; external Render connections should at least use
`sslmode=require`, with `verify-full` and a trusted CA where supported.
Never put database credentials in Vercel `NEXT_PUBLIC_*` variables.

URL schemes `postgres://`, `postgresql://` and `postgresql+psycopg://` normalize
to SQLAlchemy's installed psycopg driver. URL takes precedence over the existing
`POSTGRES_*` configuration. Each single-worker instance allows 3 pooled plus 2
additional connections, with a 10-second pool wait and 300-second recycle.
Override with `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, and
`DB_POOL_RECYCLE`. Multiply limits by instances/workers when sizing the DB.

From `cancersignal/backend`, with the intended URL securely exported:

```sh
python -m alembic heads
python -m alembic current
# Review/backup an existing DB before applying changes. No downgrade/reset.
python -m alembic upgrade head
python -m app.db.check
python -m alembic check
```

The single head is `workflow_0001`. Migrations include pgvector and the patient,
observation, rule, analysis, RAG, review, and workflow tables. A fresh synthetic
DB also needs the four canonical patients and rules; this import is deliberate,
never run automatically on startup:

```sh
python -m app.db.demo validate
python -m app.db.demo seed
python -c 'from sqlalchemy.orm import Session; from app.db.session import get_engine; from app.db.seed_rules import seed_rules; s=Session(get_engine()); seed_rules(s); s.commit(); s.close()'
python -m app.db.demo list
```

Do not run the disposable integration suite on the hosted DB. Its admin fixture
requires CREATE DATABASE; ordinary runtime does not.

## Backend

First locate the existing Render service. Apply settings to it; import root
`render.yaml` only if no service exists. The template provisions no database and
requests a free web service; it does not authorize upgrading a paid plan.
Select this deployment branch only once it is available in the connected repo.

- Runtime Docker; Dockerfile `cancersignal/backend/Dockerfile` and context
  `cancersignal/backend` (paths from repository root).
- Default target `runtime`, with locked dependencies including HTTP inference.
- Entrypoint starts `app.main:app` on `0.0.0.0:$PORT` with one worker.
- Health route `/ready`: verifies DB, vector and Alembic head; generic 503 on
  failure. `/health` checks process liveness independently.
- Set `DATABASE_URL`, `CORS_ORIGINS`, `EXTRACTION_MODEL`, `EXTRACTION_API_KEY`.
  `CORS_ORIGINS` is a JSON array of exact Vercel HTTPS origins, without paths.
- For the tested Verda configuration: `CANCERSIGNAL_EXTRACTION=llm`,
  `CANCERSIGNAL_EXTRACTION_ALLOW_LIVE=true`, `CANCERSIGNAL_EXTRACTION_ARCHITECTURE=v2`,
  `EXTRACTION_PROVIDER=verda`, `EXTRACTION_MODEL=kimi-k3-1-pro`,
  `EXTRACTION_RESPONSE_FORMAT=json_object`, `EXTRACTION_REASONING_EFFORT=none`,
  `EXTRACTION_MAX_OUTPUT_TOKENS=4096`. These are included in the Blueprint.
  Other providers/models may need different settings; optional
  `EXTRACTION_BASE_URL` must be an HTTPS endpoint.
- `CANCERSIGNAL_RETRIEVAL=auto` uses actual complete/lexical retrieval without
  a heavyweight embedding model. `CANCERSIGNAL_EXPLANATION=deterministic` builds
  the grounded explanation after real LLM extraction and deterministic rules.
  Optional hybrid Docker target requires explicit model-cache preparation.

Run migrations once before deployment. Free Render web services do not support
pre-deploy commands; run them from a trusted machine with the same revision and
secure URL. A paid existing service can use `python -m alembic upgrade head` as
a reviewed pre-deploy command. Startup never migrates or seeds.

## Frontend

Reuse the existing Vercel project. Root Directory: `cancersignal/frontend`.
Framework: Next.js, Node 22+, install `npm ci`, build `npm run build`.
`vercel.json` records the framework and commands. Set `NEXT_PUBLIC_API_URL` to
the actual backend HTTPS origin **without `/api/v1`**, then rebuild. This value
is embedded at build time. Add the resulting frontend origin to backend
`CORS_ORIGINS`, including only the preview domains actually used.

The local production build was tested with an intentionally non-routable HTTPS
origin; that test artifact is not a deployable demo. Rebuild with the real URL.
No frontend product behavior was modified.

## Verify the hosted demo

From `cancersignal/backend` (with the `llm` extra installed):

```sh
python scripts/verify_deployment.py --api-url https://BACKEND --frontend-origin https://FRONTEND
# Explicitly writes a synthetic note and analysis for a seeded synthetic UUID:
python scripts/verify_deployment.py --api-url https://BACKEND --frontend-origin https://FRONTEND --patient-id SYNTHETIC_UUID --require-v2
```

This checks health/readiness, patient reads, POST CORS preflight, invalid-input
422, completed analysis, LLM adapter selection, and persisted analysis readback.
Use an empty extraction cache or unset cache directory to prove a fresh inference
call; adapter provenance alone cannot distinguish replay. Then open the frontend,
select the canonical synthetic patient, enter a synthetic note, save and inspect
findings, source links and physician handoff. A separate browser test using the
deterministic extractor is useful but is not proof of live browser inference.

## References

- [Render Blueprint fields](https://render.com/docs/blueprint-spec)
- [Render pre-deploy availability](https://render.com/docs/deploys)
- [Render PostgreSQL/TLS](https://render.com/docs/postgresql-creating-connecting)
- [Vercel monorepos](https://vercel.com/docs/monorepos)
- [Vercel environment variables](https://vercel.com/docs/environment-variables)
