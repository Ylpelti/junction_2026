# Compact v2 deployment integration — 2026-11-15

> Historical checkpoint. See [the release verification](deployment-v2-release-verification.md)
> for resolved tests, hosted database initialization, and the final release status.

The requested branch was pushed to `origin` and verified with `git ls-remote`:
`infra/render-vercel-demo` -> `1410dda4a727923626cbc962a68aeb6f780670d3`.
Main and other branches were not pushed or merged. This remote commit includes
the English migration but not the uncommitted compact-v2 integration described below.

## Local integration snapshot (not committed or pushed)

Semantic changes were copied selectively from the shared English/semantic checkout
without modifying it. The committed frontend's newer workflow fields were retained;
only coverage types and unavailable-state mapping were added. The deployment's
DATABASE_URL/pooling support and committed extraction cache identity/logging were
retained. Snapshot includes the new narrative_semantics dependency and its synthetic
recorded regression fixture. No clinical rule or risk-model mathematics were changed.

Render configuration now explicitly selects `CANCERSIGNAL_EXTRACTION=llm`,
`CANCERSIGNAL_EXTRACTION_ARCHITECTURE=v2`, Verda `kimi-k3-1-pro`, `json_object`,
reasoning `none`, and output cap 4096. The audited v2 cohort used this model/cap;
the current snapshot is newer (`clinical-extraction-compact-en-4`,
`english-semantic-4`) and is not identical to the originally evaluated code.
No deterministic extraction or v1 fallback was used for the live checks.
The explanation stage remains the existing grounded deterministic English renderer.

## Verification

- Frontend typecheck and production webpack build passed.
- Full PostgreSQL regression: 621 passed, 1 skipped, 3 failed initially.
  One failure was a missing copied recorded synthetic fixture; adding that fixture
  resolved it. Final focused narrative/coverage/deployment subset: 28 passed.
- Two existing `test_demo_readiness.py` expectations remain incompatible:
  Nieminen's manually supplied investigation_planned and rectal-bleeding denial
  are rejected (`investigation_state_not_supported`, `outside_assertion_grammar`);
  Heikkinen's manually supplied current abdominal-pain denial is rejected
  (`outside_assertion_grammar`). The scenario labels/assertions were not weakened.
  Coordinate this contract with the semantic owner before committing the snapshot.
- Actual uvicorn HTTP + fresh disposable PostgreSQL + fresh extraction cache + real
  Kimi v2 call passed: readiness, patient reads, exact CORS preflight, invalid-ID
  422, completed analysis, semantic coverage `incomplete`, English explanation,
  and identical persisted readback. No mock inference.
- Actual Chrome browser + real API/database + fresh Kimi v2 inference passed:
  synthetic note -> compact extraction -> current bleeding finding -> English
  findings view -> persisted analysis -> physician handoff -> reload confirmation.
  Playwright: 1 passed, 24.3 seconds total. Initial browser attempt timed out before
  selecting a patient; a retry with explicit initial visibility checking passed.
- Shared local database was only read; test writes/seeding/migrations used unique
  disposable databases cleaned up by the test runners. No remote DB was touched.

## Hosted blockers

No hosted backend/frontend URL has been verified. DATABASE_URL remains absent from
the exported environment and inspected ignored files. Render/Vercel plugin discovery
still reports not installed despite the user's connection attempt; no service tools
are exposed in this session. Docker MCP catalog search found no alternative server.
The browser fallback reports Computer Use permissions not granted.

Next: make the existing Render DB URL available securely and expose the existing
hosting services; resolve the two semantic-contract tests with their owner, commit
and push the tested v2 integration, then deploy to existing services and repeat the
live API/browser checks on external URLs. Do not label the current remote commit
as compact-v2 ready and do not substitute the local test URL for a hosted deployment.
