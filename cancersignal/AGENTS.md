# CancerSignal — agent instructions

## Scope and current baseline

CancerSignal is a Junction 2026 prototype for AstraZeneca's Equitable and Effective
Cancer Care in Finland challenge. It helps nurses identify overlooked colorectal
cancer signals in synthetic patient histories and submit findings for physician
review. It does not diagnose cancer or autonomously refer patients.

This feature inventory was checked against `origin/main` at `3d44bbc` on
2026-11-14. Recheck implementation when changing it: older README and TODO prose
may lag merged code. Feature-branch and untracked work are not part of this baseline.

## Implemented on main

- Next.js/React/TypeScript/Tailwind nurse dashboard and physician queue, with
  patient history, note saving, evidence cards, urgent/review alerts, alert reasons,
  and explicitly labelled synthetic prototype data.
- FastAPI `/api/v1` routes for patients, encounters, observations, timelines,
  analyses and physician review requests; independent `/health` liveness endpoint.
- PostgreSQL 16 + pgvector in Docker Compose, SQLAlchemy records, Alembic
  migrations, reproducible synthetic patient seeds and enabled colorectal rules.
- Persisted analysis findings, evidence references, rule snapshots, provenance,
  missing information and separate model predictions. History is patient-scoped
  and excludes records at or after the current note's cutoff on both time axes.
- SUO-01 through SUO-10 deterministic colorectal rules, with Python-derived
  anaemia, iron deficiency anaemia and FIT findings. SUO-08 and SUO-09 are urgent.
- Optional Verda/OpenAI-compatible structured clinical extraction, schema and
  evidence validation, and validated response caching. Extraction is off by
  default; the structured-only demo extractor remains available.
- Independent complete/lexical/dense/hybrid RAG engine with timeline expansion,
  optional local embeddings, indexing, CLI and synthetic benchmark. The analysis
  API still uses its baseline retriever; do not describe hybrid RAG as wired in.
- QCancer-2013 numerical predictions connected to analysis responses and a
  separate nurse-dashboard card. Unknown required inputs produce
  `insufficient_data`; predictions never change rule-based review alerts.
- Persisted physician-review submissions and pending queue, connected to the
  frontend. Dismissals and physician decisions remain browser state; appointment
  information and parts of the queue still use documented demo fallbacks.

Not implemented on this baseline: a dedicated LLM explanation/referral engine,
pathway simulation (`simulation/` is a placeholder), authentication, EHR
integration, or a Finnish-validated risk model. Do not describe planned evaluation
or branch-only functionality as complete.

## Product invariants

1. The LLM extracts source-backed facts; it never computes risk, urgency, lab
   trends or dates. Python rules determine review alerts. QCancer is a separate
   Python calculation with no routing threshold.
2. Every rule retains its source and section (`lahde`, `lahde_kohta`). The current
   rule definitions live in `backend/app/db/seed_rules.py`, not `rules.csv`.
3. Findings and predictions must reference allowed source observations. Validate
   patient identity, record IDs, verbatim quotes and offsets before persistence.
   Never invent citations or silently accept invalid evidence.
4. Historical `observed_at` and `recorded_at` must both be strictly before the
   note's time t. The current note is explicit input, never retrieved history.
5. Preserve negation, uncertainty, temporal state and unknown inputs. Missing
   data is not evidence of absence and must not be converted to false.
6. Say “no signals identified”, never “no cancer”. Failed/incomplete analysis
   provides no clinical conclusion. Humans decide on investigations and referrals.
7. Use synthetic patient data only. Keep prototype, fallback and unvalidated
   outputs clearly labelled. QCancer uses a synthetic Townsend placeholder of 0
   and is not calibrated for Finland; preserve its disclaimer and bundled license.

## Architecture and contracts

| Area | Implementation / guidance |
| --- | --- |
| Public API | `backend/app/api/`, `backend/app/schemas/`, `docs/contracts.md` |
| Shared pipeline contracts | `backend/app/contracts/`, including its README and evidence validators |
| Persistence | `backend/app/models/`, `backend/app/db/`, `backend/alembic/`, `docs/data-model.md` |
| Analysis orchestration | `backend/app/services/analysis_service.py`, `backend/app/reasoning/interfaces.py` |
| Extraction | `backend/app/extraction/`, `backend/app/services/llm_extraction.py` |
| Retrieval | `backend/app/rag/`, including its README |
| Rules and lab findings | `backend/app/reasoning/`, `backend/app/db/seed_rules.py`, `docs/rulebook-colorectal.md` |
| Numerical predictions | `backend/app/risk_models/`; main also has `docs/risk-models.md` |
| Physician handoff | `backend/app/services/review_service.py`, `docs/physician-review-api.md` |
| UI and API mapping | `frontend/components/`, `frontend/lib/` |

Read the relevant contracts before changing interfaces. Keep original observations
separate from interpretations and coordinate shared schema changes. See
`backend/AGENTS.md` and `frontend/AGENTS.md` for component-specific instructions.

## Development workflow

- Inspect the current code and working-tree status first. Keep changes focused,
  preserve teammates' uncommitted work, and avoid unrelated refactors.
- Use feature branches or separate worktrees; keep main runnable. Do not push,
  merge, rebase or force-push without authorization.
- Prefer simple implementations and existing dependencies. Keep runtime
  dependencies local to their component; there is no root build/task runner.
- Run checks appropriate to the change, review the diff, and report what actually
  ran, failures and remaining limitations. Never claim unexecuted tests passed.
- Protect patient/time isolation, grounding, deterministic rules and the main
  nurse-to-physician journey with focused tests.
- Keep secrets in ignored environment files. Never commit credentials, expose
  private records in logs, or delete persistent database volumes as routine setup.
- Use cached synthetic extraction responses for offline demos. Live extraction
  requires provider configuration and explicit live-call opt-in.

## Local setup

Requires Node.js 22+, Python 3.11+ and Docker Compose for PostgreSQL.
From `cancersignal/`, copy `.env.example` to `.env` only if it does not already
exist, configure the local database password, then run:

```sh
docker compose up -d --wait db
```

Install, migrate and run the backend using `backend/AGENTS.md`; run the frontend
in a separate terminal using `frontend/AGENTS.md`. Defaults are frontend
`http://localhost:3000`, backend `http://localhost:8000`, and API docs `/docs`.
`/health` checks liveness, not database readiness.

Evaluation remains synthetic prototype evaluation, not clinical validation.
For future latest-note / note-plus-labs / full-history comparisons, keep held-out
labels independent of generation and report recall, precision, false alarms and
grounding accuracy without tuning on the held-out set.
