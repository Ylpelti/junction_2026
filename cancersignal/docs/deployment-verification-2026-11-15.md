# Deployment verification — 2026-11-15 (Europe/Helsinki)

Branch `infra/render-vercel-demo`, baseline `origin/main` at `6290872`.
Worktree `/private/tmp/cancersignal-render-demo`.

## Results actually executed

| Check | Result |
| --- | --- |
| Backend public URL | Not available; no hosted deployment performed |
| Frontend public URL | Not available; no hosted deployment performed |
| Local PostgreSQL | Connected; pgvector 0.8.7; Alembic `workflow_0001` |
| Deployment/API tests | 34 passed before adding two tests; final deployment/contract subset 7 passed |
| Python dependency consistency | `pip check` passed |
| Frontend production build | `npm run build -- --webpack` passed using an intentionally non-routable HTTPS API origin |
| Runtime Docker build | Passed, local Linux arm64 image `cancersignal-render-demo:local` |
| Runtime Docker DB check | `/health`, `/ready`, `/api/v1/patients` all 200 via TestClient in built image and real local PostgreSQL |
| Browser integration | 1 Playwright test passed with installed Chrome and real FastAPI/disposable PostgreSQL: analysis, physician handoff, decisions, dismissals, reload persistence; deterministic extraction |
| Real provider smoke | 1 passed, no response replay cache, synthetic extraction |
| Full real-inference API workflow | Passed on fresh disposable PostgreSQL DB and fresh extraction cache, actual uvicorn HTTP, seeded synthetic patient |
| HTTP failure behavior | Invalid patient ID -> 422; unavailable readiness -> generic 503 in tests |
| CORS | Exact-origin POST preflight passed in full API check |
| Diff whitespace | `git diff --check` passed |

Full live API result: completed analysis, null pipeline error, extraction method
`structured-source-demo-v1+clinical-extraction-2`, retrieval method
`cancersignal-patient-retrieval-v1.0:complete`, and identical persisted readback.
No mock provider was used in the standalone live test or full live API check.
Browser integration used the deterministic extractor; a browser session with
live inference and the public hosted path were not verified together.

## Failures and limitations

The provider rejected its default `json_schema` request settings. The standalone
live test passed with `EXTRACTION_RESPONSE_FORMAT=json_object`,
`EXTRACTION_REASONING_EFFORT=none`, and `EXTRACTION_MAX_OUTPUT_TOKENS=8192`.
Those values are included in the Render template. The first full live API attempt
failed an analysis assertion before detailed failure reporting was added; its
specific pipeline error was not captured. A repeat with safe stage reporting
completed. This is not evidence of consistent latency or reliability under load.

Initial DB tests were blocked by sandbox TCP restrictions; approved rerun passed.
A test invocation from repository root loaded the shared editable installation
instead of this worktree and failed; the final run from `cancersignal/backend`
loaded the correct isolated code and passed. Always run backend checks there.
Playwright's bundled Chromium was absent; installed Chrome passed the browser test.
Docker build was validated for local arm64, not remote amd64. No hybrid image or
model download was needed for complete/lexical retrieval.

The existing shared local database was only read. Migrations/seeding and test
writes ran in newly created, disposable test databases; those databases were
removed by their test harnesses. No remote database migrations, cloud resources,
live-service changes, pushes or merges occurred. Other worktrees were not edited.

## Remaining steps

1. Supply a PostgreSQL `DATABASE_URL` securely (Render or a Vercel-connected
   PostgreSQL provider with pgvector). None was available at verification time.
2. Identify/connect the existing Render service and Vercel project. No credentials
   or URLs were available; no duplicate services were provisioned.
3. Publish this branch through the intended Git workflow, review the remote DB
   revision, migrate once and seed only the intended synthetic demo database.
4. Configure backend secrets and exact CORS origin; deploy backend, set Vercel
   `NEXT_PUBLIC_API_URL` to its HTTPS origin, then rebuild/deploy frontend.
5. Run `scripts/verify_deployment.py` and the browser live-inference journey on
   those actual URLs. Record target architecture, cold/warm latency and failures.

See [the runbook](render-vercel-deployment.md) for exact commands, variable names,
provider configuration, and official hosting references.
