# Demo seed integration verification — 2026-11-14

The authorized Agent A demo seed and Agent C workflow implementation are integrated
from the reviewed `integration/analysis-end-to-end` working tree. The source
worktrees were preserved. The canonical source fixture, independent labels,
package-data declaration and workflow-aware reset are version controlled together.

This release verification used only a newly created disposable PostgreSQL database.
No application database seed, reset, migration or analysis was run.

- Initial seed: 66 inserted records (4 patients, 21 encounters, 41 observations).
- Repeated seed: 66 unchanged; zero inserted or updated.
- Actual Uvicorn HTTP verification passed for all four patients in both `auto`
  (complete-history) and real cached E5 `hybrid` modes.
- Verified persisted source fields, patient/time isolation, eligible labs,
  evidence references, clinical explanations and exact analysis GET readback.
- Hybrid mode was asserted; lexical fallback could not pass as hybrid.
- Tests cover index reuse/invalidation and reset preservation of unrelated patients.
- Workflow reset removes physician decisions and dismissals before their parents.

Reports: [auto](demo-pipeline-auto.json), [hybrid](demo-pipeline-hybrid.json).
Their analysis IDs refer to the disposable database, which was dropped afterward.
They are verification outputs, never clinical inputs or evaluation labels.

All 15 Hb observations preserve source values, units and timestamps. Ingestion
maps fixture LOINC `718-7` to the existing `B-Hb` alias. See the
[dataset documentation](../backend/app/db/demo_data/README.md).

Extraction was off, explanation deterministic, and external live calls disabled.
QCancer reported `insufficient_data`; no unknown predictor was fabricated.
These checks do not establish clinical accuracy or live LLM quality.

For repeatable release checks, run `RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest`
and `.venv/bin/python scripts/smoke_pipeline.py --hybrid` from the backend.
Both create their own disposable databases. `scripts/verify_demo_pipeline.py`
uses its configured database and writes analyses: to reproduce these reports,
create a disposable database, migrate it, seed rules and `app.db.demo`, export
its `POSTGRES_DB`, run the verifier with `--retrieval auto` and `--retrieval hybrid`,
and drop only that disposable database afterward.
