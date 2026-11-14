# Final integration audit — 2026-11-14

Baseline: `origin/main` at `2b6f4df` after `git fetch origin --prune`.
Integration branch: `integration/final-main-audit`, isolated at
`/private/tmp/cancersignal-final-main`. Main has not been updated.

## Outcome and commit set

- `160d3c81139ee56eb824c3db0c680a9758939192`: published Agent B implementation from draft PR #1.
- `81a2947`: merge of Agent B into current main; preserves history, no conflicts.
- `76dc6f4`: authorized demo seed and persistent workflow, with verification reports.
- A final documentation-only commit contains this inventory (see PR commit list).

[PR #1](https://github.com/Ylpelti/junction_2026/pull/1) was the only GitHub PR
returned by the all-states API at audit time. It is open/draft at `160d3c8`.
Its completed commit is included here; this audit does not close or alter PR #1.

Already in main: foundational API/data model, SUO rules, independent and integrated
hybrid RAG, optional LLM extraction, QCancer, Finnish explanation engine, physician
handoff, and A/B/C evaluation harness plus 36 synthetic cases (`2b6f4df`).
New here: persisted analysis explanations and handoff hardening from PR #1;
versioned four-patient seed; guarded patient-scoped reset; persistent dismissals,
physician decisions and queue history; workflow migration and concurrency tests.

The user explicitly authorized transferring the reviewed uncommitted backend demo
and workflow implementation. These were copied using an explicit file list after
SHA-256 comparison with the initial audit. No entire-repository staging was used.
Original worktrees were neither reset nor deleted; their recorded uncommitted
file hashes were unchanged at the preservation check. The unrelated frontend
package-lock.json was preserved and is absent from this PR's diff.

## Integration decisions and dependencies

- All foundational feature branch tips are ancestors of main: no duplicate merge.
- `integration/analysis-end-to-end` and `integration/workflow-reviewed` share
  `160d3c8`. Only the published implementation was merged, once.
- Workflow implementation in the root working tree matched the original workflow
  worktree byte-for-byte, except its integration documentation. The reviewed
  workflow-integration copy matched the root backend code and tests.
- The root demo seed matched Agent A's patient data, labels and tests. Its reset
  adds deletion of physician decisions and dismissals before parent records;
  this dependency was integrated atomically with workflow.
- `feat/demo-patients` (`0620075`) and `origin/feat/demo-patients-seed` (`f2e26e4`)
  are alternative implementations, not patch-equivalent commits. They remain
  preserved but excluded to avoid competing datasets/seed commands. Their separate
  LOINC rule aliases are not necessary for the selected ingestion mapping.
- `origin/feat/demo-reset` (`57901db`) is excluded: it resets all analyses and
  non-seed observations, including unrelated patients, lacks workflow FK cleanup,
  and targets a different seed interface. The selected reset is scoped to the four
  registered identities and requires database-name confirmation plus demo opt-in.
- `feat/pathway-simulation` is published but its worktree has unfinished extensions;
  `feat/simulation-real-model` also has active uncommitted code. Both are pending.
  The untracked root `junction2026/` simulation copy remains untouched.
- A/B/C evaluation is already merged; its detached worktree was clean. No
  unpublished evaluation changes were imported and no paid evaluation run occurred.
- Only committed PR #1 frontend changes are included. Active frontend work and
  the unrelated lockfile are excluded. Backend dismissal/decision endpoints are
  implemented; UI wiring for those actions remains a separate task.

## Verification

All tests used the repository's existing backend `.venv`, with `PYTHONPATH` and cwd
pointing to the isolated integration backend. Database credentials were inherited
in memory without logging them. Live extraction/explanation were explicitly off.

| Check | Result |
| --- | --- |
| `RUN_DATABASE_TESTS=1 python -m pytest -q -ra` | 532 passed, 1 skipped, 18.46 seconds |
| Skipped | `test_real_provider_validates_synthetic_extraction`: paid API opt-in not authorized |
| `python -m pip check` | No broken requirements |
| `alembic heads` | Single `workflow_0001` head |
| Alembic `check` | No new upgrade operations on freshly upgraded disposable DB and after round trip |
| Migration round trip | upgrade → check → downgrade base → upgrade → check passed |
| `scripts/smoke_pipeline.py --hybrid` | Actual Uvicorn/PostgreSQL lexical and real cached E5 hybrid passed; persisted explanation and idempotent handoff |
| Four-patient HTTP verifier | 4/4 complete-history and 4/4 hybrid passed; saved sources, labs, evidence and analysis readback |
| Demo seeding | 66 inserted initially; repeat 66 unchanged, 0 updates/inserts |
| `npm run typecheck` | Passed in isolated checkout |
| `npm run build -- --webpack` | Passed in isolated checkout |
| `git diff --check` | Passed |

Coverage includes patients/observations, indexing reuse/invalidation, hybrid RAG,
mocked/cache LLM extraction integration, QCancer, clinical explanation, handoff,
dismissals/decisions, demo reset and concurrent updates. Live paid LLM inference
and subjective clinical quality were not tested. The backend's first sandboxed
attempt had local-socket permission errors (380 passed, 110 setup errors); the
full rerun with local database access passed as reported above.

The frontend checks reused installed dependencies through a temporary symlink;
only the isolated checkout received build output. No `npm install` or lockfile
update occurred. The temporary link was removed after verification. No interactive
browser acceptance test or frontend test runner was run.

Alembic chain: `0001 → 0002 → rag_0001 → review_0001 → workflow_0001`.
Workflow downgrade refuses to discard recorded human actions. Disposable empty
migration reversibility and workflow metadata/FKs were tested. `alembic check`
excludes reflected tables outside central metadata, including RAG cache tables;
RAG behavior was checked through database tests and real hybrid smoke.
No migration/reset was executed against the application database. All release
verification databases were created with random names and dropped afterward.

## Before merge and deployment

Obtain explicit approval before updating origin/main. Recheck remote main and PR
checks if new commits arrive. Do not bypass branch protections. Apply the reviewed
migration through the normal deployment process, then seed/index deliberately;
this audit has not migrated or reset the application database. Workflow UI wiring,
active simulation work, and live-provider verification remain separate work.
Actors are unverified demo labels, not authentication. No clinical validation is
claimed; QCancer can legitimately report insufficient data. Clinical explanations
in this verification used deterministic mode.

## Branch inventory

Every local and remote ref is listed below. “Files” means feature contribution
relative to its merge-base with origin/main (`git diff origin/main...ref`), so
ancestor branches have no new files. Main's subsequent changes are not mistakenly
reported as feature deletions. “Published” means the tip is reachable from a remote
ref, even where the local branch name itself was never pushed.

### `chore/cancersignal-setup`

- Commit: `a4294564661a8d4427935fd088fa20d0081abfc9`. Upstream: `origin/main`. Published tip: yes.
- Purpose: cancersignal setup. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `docs/update-agent-instructions`

- Commit: `7384cc7b4d49f14be3b68005898917a8df749856`. Upstream: `origin/main`. Published tip: yes.
- Purpose: update agent instructions. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/api-analysis-pipeline`

- Commit: `28702734044418ee42ba4db58c77fb855fb32e01`. Upstream: `origin/main`. Published tip: yes.
- Purpose: api analysis pipeline. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/backend-foundation`

- Commit: `b2b98d497fa9079819473d62471c69a097168ca5`. Upstream: `origin/main`. Published tip: yes.
- Purpose: backend foundation. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/clinical-explanation-engine`

- Commit: `84409a615244a902ea52207d3ff85c896a9c8eea`. Upstream: `origin/main`. Published tip: yes.
- Purpose: clinical explanation engine. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/clinical-llm-extraction`

- Commit: `25c8fe384e2856c7f13d57541520c2b724e84667`. Upstream: `origin/main`. Published tip: yes.
- Purpose: clinical llm extraction. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/colorectal-rules`

- Commit: `d25ae1319918ca499a9197589c26913500da9165`. Upstream: `origin/feat/colorectal-rules`. Published tip: yes.
- Purpose: colorectal rules. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/demo-patients`

- Commit: `06200750011639d8abe94dbe8dd5fd0197b73b7c`. Upstream: `origin/feat/demo-patients`. Published tip: yes.
- Purpose: demo patients. Excluded/pending; see integration decisions above.
- Commits outside main:

```text
0620075 feat(backend): seed four colorectal evaluation demo patients
```

Patch equivalence (`+` = not present in main):

```text
+ 06200750011639d8abe94dbe8dd5fd0197b73b7c
```

Files contributed beyond main:

```text
cancersignal/README.md
cancersignal/backend/app/db/seed.py
cancersignal/backend/data/patients/demo_cases.json
cancersignal/backend/tests/test_data_model.py
cancersignal/backend/tests/test_demo_patients.py
```

### `feat/hybrid-rag-integration`

- Commit: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Upstream: `origin/main`. Published tip: yes.
- Purpose: hybrid rag integration. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/pathway-simulation`

- Commit: `16fe694449665f7f36be22a687a6d6ee935d386e`. Upstream: `origin/feat/pathway-simulation`. Published tip: yes.
- Purpose: pathway simulation. Excluded/pending; see integration decisions above.
- Commits outside main:

```text
16fe694 feat(simulation): add isolated paired healthcare pathway simulation
```

Patch equivalence (`+` = not present in main):

```text
+ 16fe694449665f7f36be22a687a6d6ee935d386e
```

Files contributed beyond main:

```text
junction2026/.gitignore
junction2026/README.md
junction2026/REPORT.md
junction2026/cancersignal_sim/__init__.py
junction2026/cancersignal_sim/__main__.py
junction2026/cancersignal_sim/cli.py
junction2026/cancersignal_sim/engine.py
junction2026/cancersignal_sim/inputs.py
junction2026/cancersignal_sim/reporting.py
junction2026/config/demo.json
junction2026/pyproject.toml
junction2026/tests/test_simulation.py
```

### `feat/persistent-clinical-workflow`

- Commit: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Upstream: `none`. Published tip: yes.
- Purpose: persistent clinical workflow. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/physician-review-workflow`

- Commit: `432becff143f1eec31359ad761bf9b9fe250783d`. Upstream: `origin/main`. Published tip: yes.
- Purpose: physician review workflow. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/rag-retrieval-engine`

- Commit: `347753cd14f75ddbd71bb55a9dfee4dca445d243`. Upstream: `origin/main`. Published tip: yes.
- Purpose: rag retrieval engine. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/shared-pipeline-contracts`

- Commit: `51cc635dcde88bff47e81687df60c614f94e12bc`. Upstream: `origin/main`. Published tip: yes.
- Purpose: shared pipeline contracts. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/simulation-real-model`

- Commit: `84409a615244a902ea52207d3ff85c896a9c8eea`. Upstream: `none`. Published tip: yes.
- Purpose: simulation real model. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/standardized-data-model`

- Commit: `d96167678e59bf55590108c7a17a9c6b48867637`. Upstream: `origin/main`. Published tip: yes.
- Purpose: standardized data model. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `feat/synthetic-demo-patients`

- Commit: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Upstream: `none`. Published tip: yes.
- Purpose: synthetic demo patients. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `integration/analysis-end-to-end`

- Commit: `160d3c81139ee56eb824c3db0c680a9758939192`. Upstream: `origin/integration/analysis-end-to-end`. Published tip: yes.
- Purpose: analysis end to end. Integrated once via PR #1.
- Commits outside main:

```text
160d3c8 feat(integration): persist Finnish analysis explanations and harden handoff
```

Patch equivalence (`+` = not present in main):

```text
+ 160d3c81139ee56eb824c3db0c680a9758939192
```

Files contributed beyond main:

```text
cancersignal/.env.example
cancersignal/backend/app/core/config.py
cancersignal/backend/app/schemas/analysis.py
cancersignal/backend/app/services/analysis_service.py
cancersignal/backend/app/services/clinical_explanation.py
cancersignal/backend/scripts/smoke_pipeline.py
cancersignal/backend/tests/test_live_extraction_smoke.py
cancersignal/backend/tests/test_pipeline_handoff.py
cancersignal/docs/end-to-end-integration.md
cancersignal/frontend/components/CancerSignalApp.tsx
cancersignal/frontend/components/ClinicalExplanationCard.tsx
cancersignal/frontend/components/NurseView.tsx
cancersignal/frontend/components/PhysicianView.tsx
cancersignal/frontend/lib/api.ts
cancersignal/frontend/lib/flags.ts
cancersignal/frontend/lib/mappers.ts
cancersignal/frontend/lib/types.ts
```

### `integration/workflow-reviewed`

- Commit: `160d3c81139ee56eb824c3db0c680a9758939192`. Upstream: `none`. Published tip: yes.
- Purpose: workflow reviewed. Integrated once via PR #1.
- Commits outside main:

```text
160d3c8 feat(integration): persist Finnish analysis explanations and harden handoff
```

Patch equivalence (`+` = not present in main):

```text
+ 160d3c81139ee56eb824c3db0c680a9758939192
```

Files contributed beyond main:

```text
cancersignal/.env.example
cancersignal/backend/app/core/config.py
cancersignal/backend/app/schemas/analysis.py
cancersignal/backend/app/services/analysis_service.py
cancersignal/backend/app/services/clinical_explanation.py
cancersignal/backend/scripts/smoke_pipeline.py
cancersignal/backend/tests/test_live_extraction_smoke.py
cancersignal/backend/tests/test_pipeline_handoff.py
cancersignal/docs/end-to-end-integration.md
cancersignal/frontend/components/CancerSignalApp.tsx
cancersignal/frontend/components/ClinicalExplanationCard.tsx
cancersignal/frontend/components/NurseView.tsx
cancersignal/frontend/components/PhysicianView.tsx
cancersignal/frontend/lib/api.ts
cancersignal/frontend/lib/flags.ts
cancersignal/frontend/lib/mappers.ts
cancersignal/frontend/lib/types.ts
```

### `main`

- Commit: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Upstream: `origin/main`. Published tip: yes.
- Purpose: main. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin`

- Commit: `2b6f4dfc3974e182a7d35c822aac3f006e3910f8`. Upstream: `none`. Published tip: yes.
- Purpose: origin. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/codex/update-qcancer-main`

- Commit: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Upstream: `none`. Published tip: yes.
- Purpose: update qcancer main. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/feat/colorectal-rules`

- Commit: `d25ae1319918ca499a9197589c26913500da9165`. Upstream: `none`. Published tip: yes.
- Purpose: colorectal rules. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/feat/demo-patients`

- Commit: `06200750011639d8abe94dbe8dd5fd0197b73b7c`. Upstream: `none`. Published tip: yes.
- Purpose: demo patients. Excluded/pending; see integration decisions above.
- Commits outside main:

```text
0620075 feat(backend): seed four colorectal evaluation demo patients
```

Patch equivalence (`+` = not present in main):

```text
+ 06200750011639d8abe94dbe8dd5fd0197b73b7c
```

Files contributed beyond main:

```text
cancersignal/README.md
cancersignal/backend/app/db/seed.py
cancersignal/backend/data/patients/demo_cases.json
cancersignal/backend/tests/test_data_model.py
cancersignal/backend/tests/test_demo_patients.py
```

### `origin/feat/demo-patients-seed`

- Commit: `f2e26e445e1a55ca30df93fdc3813fb91bfba72a`. Upstream: `none`. Published tip: yes.
- Purpose: demo patients seed. Excluded/pending; see integration decisions above.
- Commits outside main:

```text
f2e26e4 feat(backend): versioned demo patients with LOINC lab codes and seed script
```

Patch equivalence (`+` = not present in main):

```text
+ f2e26e445e1a55ca30df93fdc3813fb91bfba72a
```

Files contributed beyond main:

```text
cancersignal/README.md
cancersignal/backend/AGENTS.md
cancersignal/backend/app/db/seed_demo.py
cancersignal/backend/app/reasoning/derived_findings.py
cancersignal/backend/data/patients/demo_patients.json
cancersignal/backend/tests/test_derived_findings.py
cancersignal/backend/tests/test_seed_demo.py
cancersignal/docs/backend-todo.md
```

### `origin/feat/demo-reset`

- Commit: `57901dba01ed90fc39ecf174cf3e7351742f9022`. Upstream: `none`. Published tip: yes.
- Purpose: demo reset. Excluded/pending; see integration decisions above.
- Commits outside main:

```text
57901db feat(backend): add local demo reset command
6292a87 Merge remote-tracking branch 'origin/main' into feat/demo-reset
e518aeb feat(backend): one-command local demo database reset
```

Patch equivalence (`+` = not present in main):

```text
+ e518aebaf35854c1943abc8f135c9775aaf7db15
+ 57901dba01ed90fc39ecf174cf3e7351742f9022
```

Files contributed beyond main:

```text
cancersignal/README.md
cancersignal/backend/app/db/reset_demo.py
cancersignal/backend/tests/test_reset_demo.py
```

### `origin/feat/eval-cases`

- Commit: `bce28e15870f36521e3d998aa801f3a23519d738`. Upstream: `none`. Published tip: yes.
- Purpose: eval cases. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/feat/hide-qcancer-nurse`

- Commit: `4d77016b563955253ac44bddaec6d4e9a55c378a`. Upstream: `none`. Published tip: yes.
- Purpose: hide qcancer nurse. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/feat/nurse-dashboard-api`

- Commit: `718523c3dca07fcfec052be84cae0940748a6930`. Upstream: `none`. Published tip: yes.
- Purpose: nurse dashboard api. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/feat/pathway-simulation`

- Commit: `16fe694449665f7f36be22a687a6d6ee935d386e`. Upstream: `none`. Published tip: yes.
- Purpose: pathway simulation. Excluded/pending; see integration decisions above.
- Commits outside main:

```text
16fe694 feat(simulation): add isolated paired healthcare pathway simulation
```

Patch equivalence (`+` = not present in main):

```text
+ 16fe694449665f7f36be22a687a6d6ee935d386e
```

Files contributed beyond main:

```text
junction2026/.gitignore
junction2026/README.md
junction2026/REPORT.md
junction2026/cancersignal_sim/__init__.py
junction2026/cancersignal_sim/__main__.py
junction2026/cancersignal_sim/cli.py
junction2026/cancersignal_sim/engine.py
junction2026/cancersignal_sim/inputs.py
junction2026/cancersignal_sim/reporting.py
junction2026/config/demo.json
junction2026/pyproject.toml
junction2026/tests/test_simulation.py
```

### `origin/feat/qcancer-and-rule-adapter`

- Commit: `f49030fb36aefd2b81650bd8cf9934facbc95d2b`. Upstream: `none`. Published tip: yes.
- Purpose: qcancer and rule adapter. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/feat/wire-llm-extraction`

- Commit: `4ec5a4e27bf49ef91419002709435906b7e5588e`. Upstream: `none`. Published tip: yes.
- Purpose: wire llm extraction. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/integration/analysis-end-to-end`

- Commit: `160d3c81139ee56eb824c3db0c680a9758939192`. Upstream: `none`. Published tip: yes.
- Purpose: analysis end to end. Integrated once via PR #1.
- Commits outside main:

```text
160d3c8 feat(integration): persist Finnish analysis explanations and harden handoff
```

Patch equivalence (`+` = not present in main):

```text
+ 160d3c81139ee56eb824c3db0c680a9758939192
```

Files contributed beyond main:

```text
cancersignal/.env.example
cancersignal/backend/app/core/config.py
cancersignal/backend/app/schemas/analysis.py
cancersignal/backend/app/services/analysis_service.py
cancersignal/backend/app/services/clinical_explanation.py
cancersignal/backend/scripts/smoke_pipeline.py
cancersignal/backend/tests/test_live_extraction_smoke.py
cancersignal/backend/tests/test_pipeline_handoff.py
cancersignal/docs/end-to-end-integration.md
cancersignal/frontend/components/CancerSignalApp.tsx
cancersignal/frontend/components/ClinicalExplanationCard.tsx
cancersignal/frontend/components/NurseView.tsx
cancersignal/frontend/components/PhysicianView.tsx
cancersignal/frontend/lib/api.ts
cancersignal/frontend/lib/flags.ts
cancersignal/frontend/lib/mappers.ts
cancersignal/frontend/lib/types.ts
```

### `origin/main`

- Commit: `2b6f4dfc3974e182a7d35c822aac3f006e3910f8`. Upstream: `none`. Published tip: yes.
- Purpose: main. Already included in main; no integration needed.

Files contributed beyond main:

None.

### `origin/test/claude-testfile`

- Commit: `4011e5febba2013250ff0db2cd9d2703bb4dec28`. Upstream: `none`. Published tip: yes.
- Purpose: claude testfile. Already included in main; no integration needed.

Files contributed beyond main:

None.

## Worktree inventory

All 12 original registered worktrees were accessible and individually inspected,
including untracked files. A scan of matching directories directly under
`/private/tmp` found no additional Git worktrees beyond those registered.
Temporary explanation/review directories without `.git` are not worktrees.
Ignored environments, caches and build outputs were observed but not imported.

### `/Users/joonavanska/junction_2026`

HEAD: `160d3c81139ee56eb824c3db0c680a9758939192`. Branch: `integration/analysis-end-to-end`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

```text
M cancersignal/backend/app/api/router.py
 M cancersignal/backend/app/api/routes/reviews.py
 M cancersignal/backend/app/models/__init__.py
 M cancersignal/backend/app/models/review.py
 M cancersignal/backend/app/schemas/reviews.py
 M cancersignal/backend/app/services/review_service.py
 M cancersignal/backend/pyproject.toml
 M cancersignal/backend/tests/test_api_contract.py
 M cancersignal/docs/backend-todo.md
 M cancersignal/docs/physician-review-api.md
 M cancersignal/frontend/package-lock.json
?? cancersignal/backend/alembic/versions/workflow_0001_persistent_actions.py
?? cancersignal/backend/app/api/routes/workflow.py
?? cancersignal/backend/app/db/demo.py
?? cancersignal/backend/app/db/demo_data/
?? cancersignal/backend/app/models/workflow.py
?? cancersignal/backend/app/schemas/workflow.py
?? cancersignal/backend/app/services/workflow_service.py
?? cancersignal/backend/scripts/verify_demo_pipeline.py
?? cancersignal/backend/tests/fixtures/demo/
?? cancersignal/backend/tests/test_demo.py
?? cancersignal/backend/tests/test_workflow.py
?? cancersignal/backend/tests/test_workflow_demo_reset.py
?? cancersignal/docs/demo-pipeline-auto.json
?? cancersignal/docs/demo-pipeline-hybrid.json
?? cancersignal/docs/demo-seed-integration.md
?? cancersignal/docs/workflow-persistence-api.md
?? demo-patients/
?? junction2026/
```

### `/private/tmp/cancersignal-agent-instructions`

HEAD: `7384cc7b4d49f14be3b68005898917a8df749856`. Branch: `docs/update-agent-instructions`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

Clean (no uncommitted or untracked source files).

### `/private/tmp/cancersignal-hybrid-integration`

HEAD: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Branch: `feat/hybrid-rag-integration`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

Clean (no uncommitted or untracked source files).

### `/private/tmp/cancersignal-real-integration`

HEAD: `84409a615244a902ea52207d3ff85c896a9c8eea`. Branch: `feat/simulation-real-model`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

```text
M cancersignal/backend/app/extraction/service.py
 D cancersignal/simulation/.gitkeep
?? cancersignal/simulation/.gitignore
?? cancersignal/simulation/LEGACY_README.md
?? cancersignal/simulation/PRIORITY_REVIEW_FINDINGS.md
?? cancersignal/simulation/README.md
?? cancersignal/simulation/REAL_MODEL_README.md
?? cancersignal/simulation/REAL_MODEL_REPORT.md
?? cancersignal/simulation/REPORT.md
?? cancersignal/simulation/WORKFLOW_COMPARISON.md
?? cancersignal/simulation/WORKFLOW_FINDINGS.md
?? cancersignal/simulation/cancersignal_sim/
?? cancersignal/simulation/config/
?? cancersignal/simulation/data/
?? cancersignal/simulation/integration_tests/
?? cancersignal/simulation/pyproject.toml
?? cancersignal/simulation/results/
?? cancersignal/simulation/tests/
```

### `/private/tmp/cancersignal-simulation-zPVwqR`

HEAD: `16fe694449665f7f36be22a687a6d6ee935d386e`. Branch: `feat/pathway-simulation`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

```text
M junction2026/README.md
 M junction2026/REPORT.md
 M junction2026/cancersignal_sim/cli.py
 M junction2026/cancersignal_sim/engine.py
 M junction2026/cancersignal_sim/reporting.py
?? junction2026/WORKFLOW_COMPARISON.md
?? junction2026/WORKFLOW_FINDINGS.md
?? junction2026/cancersignal_sim/real_cache.py
?? junction2026/cancersignal_sim/real_inference.py
?? junction2026/cancersignal_sim/real_study.py
?? junction2026/cancersignal_sim/study.py
?? junction2026/cancersignal_sim/study_report.py
?? junction2026/config/real_model.json
?? junction2026/config/workflows.json
?? junction2026/data/
?? junction2026/results/
?? junction2026/tests/legacy_traces.json
?? junction2026/tests/test_real_model.py
?? junction2026/tests/test_workflows.py
```

### `/private/tmp/cancersignal-workflow`

HEAD: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Branch: `feat/persistent-clinical-workflow`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

```text
M cancersignal/backend/app/api/router.py
 M cancersignal/backend/app/api/routes/reviews.py
 M cancersignal/backend/app/models/__init__.py
 M cancersignal/backend/app/models/review.py
 M cancersignal/backend/app/schemas/reviews.py
 M cancersignal/backend/app/services/review_service.py
 M cancersignal/backend/tests/test_api_contract.py
 M cancersignal/docs/backend-todo.md
 M cancersignal/docs/physician-review-api.md
?? cancersignal/backend/alembic/versions/workflow_0001_persistent_actions.py
?? cancersignal/backend/app/api/routes/workflow.py
?? cancersignal/backend/app/models/workflow.py
?? cancersignal/backend/app/schemas/workflow.py
?? cancersignal/backend/app/services/workflow_service.py
?? cancersignal/backend/tests/test_workflow.py
?? cancersignal/docs/workflow-persistence-api.md
```

### `/private/tmp/cancersignal-workflow-integration`

HEAD: `160d3c81139ee56eb824c3db0c680a9758939192`. Branch: `integration/workflow-reviewed`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

```text
M cancersignal/backend/app/api/router.py
 M cancersignal/backend/app/api/routes/reviews.py
 M cancersignal/backend/app/models/__init__.py
 M cancersignal/backend/app/models/review.py
 M cancersignal/backend/app/schemas/reviews.py
 M cancersignal/backend/app/services/review_service.py
 M cancersignal/backend/tests/test_api_contract.py
 M cancersignal/docs/backend-todo.md
 M cancersignal/docs/physician-review-api.md
?? cancersignal/backend/alembic/versions/workflow_0001_persistent_actions.py
?? cancersignal/backend/app/api/routes/workflow.py
?? cancersignal/backend/app/db/demo.py
?? cancersignal/backend/app/db/demo_data/
?? cancersignal/backend/app/models/workflow.py
?? cancersignal/backend/app/schemas/workflow.py
?? cancersignal/backend/app/services/workflow_service.py
?? cancersignal/backend/tests/fixtures/demo/
?? cancersignal/backend/tests/test_demo.py
?? cancersignal/backend/tests/test_workflow.py
?? cancersignal/backend/tests/test_workflow_demo_reset.py
?? cancersignal/docs/workflow-persistence-api.md
```

### `/private/tmp/junction-demo-patients`

HEAD: `06200750011639d8abe94dbe8dd5fd0197b73b7c`. Branch: `feat/demo-patients`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

Clean (no uncommitted or untracked source files).

### `/private/tmp/junction-demo-patients-seed`

HEAD: `f2e26e445e1a55ca30df93fdc3813fb91bfba72a`. Branch: `detached`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

Clean (no uncommitted or untracked source files).

### `/private/tmp/junction-eval-cases`

HEAD: `12200d79ee0be94b9875a78c9ecc52e4eb9ac371`. Branch: `detached`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

Clean (no uncommitted or untracked source files).

### `/private/tmp/junction-qcancer-integration`

HEAD: `3d44bbcba39f98b70e6837eee587e9a35f41083a`. Branch: `detached`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

Clean (no uncommitted or untracked source files).

### `/Users/joonavanska/junction_2026/demo-patients`

HEAD: `42ea781dbaf7dd38077238bf3bfbabe860ac4cc4`. Branch: `feat/synthetic-demo-patients`. Committed contribution/publishing status is given above; detached commits are already in main or the corresponding preserved demo branch.

```text
M cancersignal/backend/pyproject.toml
?? cancersignal/backend/app/db/demo.py
?? cancersignal/backend/app/db/demo_data/
?? cancersignal/backend/tests/fixtures/demo/
?? cancersignal/backend/tests/test_demo.py
```

## Final changed files relative to main

```text
M	cancersignal/.env.example
A	cancersignal/backend/alembic/versions/workflow_0001_persistent_actions.py
M	cancersignal/backend/app/api/router.py
M	cancersignal/backend/app/api/routes/reviews.py
A	cancersignal/backend/app/api/routes/workflow.py
M	cancersignal/backend/app/core/config.py
A	cancersignal/backend/app/db/demo.py
A	cancersignal/backend/app/db/demo_data/README.md
A	cancersignal/backend/app/db/demo_data/patients.json
M	cancersignal/backend/app/models/__init__.py
M	cancersignal/backend/app/models/review.py
A	cancersignal/backend/app/models/workflow.py
M	cancersignal/backend/app/schemas/analysis.py
M	cancersignal/backend/app/schemas/reviews.py
A	cancersignal/backend/app/schemas/workflow.py
M	cancersignal/backend/app/services/analysis_service.py
A	cancersignal/backend/app/services/clinical_explanation.py
M	cancersignal/backend/app/services/review_service.py
A	cancersignal/backend/app/services/workflow_service.py
M	cancersignal/backend/pyproject.toml
A	cancersignal/backend/scripts/smoke_pipeline.py
A	cancersignal/backend/scripts/verify_demo_pipeline.py
A	cancersignal/backend/tests/fixtures/demo/labels.json
M	cancersignal/backend/tests/test_api_contract.py
A	cancersignal/backend/tests/test_demo.py
A	cancersignal/backend/tests/test_live_extraction_smoke.py
A	cancersignal/backend/tests/test_pipeline_handoff.py
A	cancersignal/backend/tests/test_workflow.py
A	cancersignal/backend/tests/test_workflow_demo_reset.py
M	cancersignal/docs/backend-todo.md
A	cancersignal/docs/demo-pipeline-auto.json
A	cancersignal/docs/demo-pipeline-hybrid.json
A	cancersignal/docs/demo-seed-integration.md
A	cancersignal/docs/end-to-end-integration.md
M	cancersignal/docs/physician-review-api.md
A	cancersignal/docs/workflow-persistence-api.md
M	cancersignal/frontend/components/CancerSignalApp.tsx
A	cancersignal/frontend/components/ClinicalExplanationCard.tsx
M	cancersignal/frontend/components/NurseView.tsx
M	cancersignal/frontend/components/PhysicianView.tsx
M	cancersignal/frontend/lib/api.ts
M	cancersignal/frontend/lib/flags.ts
M	cancersignal/frontend/lib/mappers.ts
M	cancersignal/frontend/lib/types.ts
```

This inventory document is the additional documentation-only change.
