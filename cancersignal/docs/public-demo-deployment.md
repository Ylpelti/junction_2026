# Public dynamic demo deployment

This repository includes a Render Blueprint at the repository root. It creates:

- `cancersignal-web`: the Next.js dashboard.
- `cancersignal-api`: the FastAPI analysis service.
- `cancersignal-demo-db`: PostgreSQL for synthetic demo records.

The browser sends `/api/v1/*` requests to the same public frontend origin. Next.js
rewrites those requests to the public FastAPI service URL. This keeps browser
requests same-origin and avoids browser CORS configuration.

## Publish

1. Sign in to Render and create a Blueprint from the GitHub repository.
2. Select the branch/commit you want to demonstrate and review the three resources
   defined in `render.yaml`.
3. Apply the Blueprint and wait for both web services to become healthy.
4. Open the `cancersignal-web` URL. Confirm the synthetic patients load, run a
   note analysis and send one result to the physician queue.

No LLM API key is configured. The default structured-source extractor and
deterministic demonstration rules run in the FastAPI process. Startup applies
Alembic migrations and idempotently seeds the synthetic fixture records and
colorectal demo rules.

## Limits

- Use only synthetic patient data. The public service is a prototype, not a
  clinical product. Do not enter real patient or personal information.
- The public demo allows visitors to create synthetic notes, analyses and review
  requests. The database is shared; these writes can affect what later visitors
  see. Reset the demo database through the documented safe reset procedure when
  needed.
- Render free web services may spin down when idle, so the first request can be
  slow. Free Render Postgres expires 30 days after creation. See
  [Render free instance limits](https://render.com/docs/free).
- The database and web services are public internet infrastructure. Keep secrets
  in Render's environment settings, never in GitHub. The demo does not add user
  authentication or per-user data isolation.
- No clinical validation, Finnish-calibrated risk estimate or measured waiting-
  time improvement is provided by this deployment.

For a longer-lived deployment, use paid persistent hosting and add authentication,
rate limiting and an explicit demo reset workflow before inviting unrestricted
traffic.
