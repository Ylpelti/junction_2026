# Compact v2 release verification — 2026-11-15

Continues `infra/render-vercel-demo` from `1410dda`, preserving the English
migration at `6290872`. Semantic source was selectively integrated from the
semantic owner's snapshot, including compact/narrative/semantic version 4.
The source checkout was not modified. The newer frontend workflow fields and
extraction cache identity/logging were retained.

Render explicitly selects real Verda `kimi-k3-1-pro` extraction, architecture v2,
JSON-object output, reasoning disabled and output-token cap 4096. No v1 or
structured-only extraction fallback is enabled. Grounded English explanation
rendering remains deterministic, distinct from actual LLM fact extraction.

## Resolved integration assertions

The old manually authored English scenario test expected every schema-valid fact
to survive. The semantic owner's narrative audit explicitly documents rejection
of anatomically ambiguous bleeding denials and broad abdominal-symptom denials.
The Nieminen source also says referral, whereas the mocked fact says plan.
The test now preserves all original scenarios and source text, asserts each exact
quarantine reason, verifies accepted states and incomplete coverage, and checks
that replay retains identical diagnostics. No validator grammar, clinical label,
source observation, rule threshold or numerical risk calculation was changed to
make the test pass.

Full regression: **624 passed, 1 skipped** in 18.97 seconds against disposable
local PostgreSQL. The skipped test is the separately opted-in live-inference test.
Frontend typecheck/production webpack build previously passed on this snapshot;
no frontend production code changed after those checks. The live browser test is
separate from the mocked/offline suite.

## Hosted PostgreSQL

The supplied DATABASE_URL was verified over TLS without printing it. Before
migration the public schema had zero tables and no Alembic revision; pgvector
was available. Existing migrations upgraded this empty database to `workflow_0001`.
`alembic check`: no new upgrade operations. Enabled pgvector version: 0.8.7.

Only after migration, the canonical synthetic demo importer and rule seed ran.
Initial counts: 4 patients, 41 observations, 10 rules. No real patient data was
present, and no reset, downgrade, DROP, or destructive migration was performed
against the hosted database. Subsequent verification creates explicitly synthetic
notes/analyses/review requests.

## Hosting access

The Render and Vercel integrations are still reported as not installed, and no
hosting-management tools are exposed. No API token or web-service/project URL
has been supplied. The prior native-browser fallback lacked Computer Use
permissions. Consequently no external frontend/backend deployment is claimed.

Once service access is available: use the existing Render service with this branch,
configure its backend-only secrets and exact frontend CORS origin, set Vercel's
NEXT_PUBLIC_API_URL before building, and run the included verification script and
live-browser test on actual external URLs. Do not create duplicate or paid services.

## Fresh hosted-database live browser result

Actual Chrome Playwright verification passed: **1 test, 23.0 seconds** total.
The frontend and FastAPI process ran locally, while PostgreSQL was the supplied
hosted database. Real Kimi compact-v2 extraction used a fresh unique cache.
The test verified current bleeding findings, English explanation, persisted
analysis equality, physician handoff and reload confirmation. This is not an
external frontend/backend deployment test. No mocked inference was used.

Final Docker runtime build passed (local Linux arm64), image
`cancersignal-render-demo:v2`, manifest-list digest
`sha256:64eb447a47da3d1c3dacce95762cf851393f61a6cd27ed26a82df46aa4dea41d`.
Remote hosting architecture/runtime and externally served CORS remain to be tested.
