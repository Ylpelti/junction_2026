"""Reset the LOCAL demo database to the same starting state every time.

    python -m app.db.reset_demo          # dry run: shows what would be deleted, deletes nothing
    python -m app.db.reset_demo --yes    # delete demo-created rows, then re-run the seeds

In one transaction it deletes everything the demo creates:
- every analysis and its findings, trigger results and review requests;
- every observation, embedding and encounter whose ID is not produced by the seed,
  for example notes the nurse saved during the demo.

Then it re-runs seed() and seed_rules() (and seed_demo() when that module exists),
so missing seed rows come back. Seed IDs are computed by running the real seed
functions against a recorder; they are never hard-coded.

Safety: refuses to run unless the database host is localhost, 127.0.0.1 or ::1.
Patients are never deleted. Observations of patients that were created outside
the seeds (for example by hand through the API) ARE deleted, because their IDs
are not seed IDs.
"""
import argparse
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.seed import seed
from app.models import (
    AnalysisRun, ClinicalFinding, Encounter, FindingEvidence, Observation, ObservationEmbedding,
    TriggerResult, TriggerResultEvidence,
)
from app.models.review import PhysicianReviewRequest

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class NotLocalDatabase(SystemExit):
    pass


def require_local_host(host: str) -> None:
    """Never touch anything but a local database."""
    if host.strip().strip("[]").lower() not in LOCAL_HOSTS:
        raise NotLocalDatabase(f"Refusing to reset: database host {host!r} is not localhost, 127.0.0.1 or ::1.")


class _Recorder:
    """Stands in for a Session: records the IDs the seed functions would insert, inserts nothing."""

    def __init__(self):
        self.ids: dict[str, set] = {}

    def execute(self, statement, *args, **kwargs):
        params = statement.compile(dialect=postgresql.dialect()).params
        self.ids.setdefault(statement.table.name, set()).add(params["id"])


def _seed_functions():
    # Imported here, not at module level (tests/rag/test_independence.py; same as seed.py main()).
    from app.db.seed_rules import seed_rules
    functions = [seed, seed_rules]
    try:
        from app.db.seed_demo import seed_demo  # versioned demo patients, when that branch is merged
    except ImportError:
        seed_demo = None
    if seed_demo is not None:
        functions.append(seed_demo)
    return functions


def seed_ids() -> dict[str, set]:
    """IDs per table that the seeds produce, computed with the seeds' own synthetic_id() logic."""
    recorder = _Recorder()
    for function in _seed_functions():
        function(recorder)
    return recorder.ids


def _chunk_model():
    # rag_embedding_chunks references observations (ON DELETE CASCADE); delete explicitly to report counts.
    from app.rag.storage import EmbeddingChunk
    return EmbeddingChunk


def plan(ids: dict[str, set]) -> list[tuple[str, object, object]]:
    """(table, model, where clause) in foreign-key-safe deletion order. None = all rows."""
    keep_observations = sorted(ids.get(Observation.__tablename__, set()), key=str)
    keep_encounters = sorted(ids.get(Encounter.__tablename__, set()), key=str)
    chunks = _chunk_model()
    return [
        ("physician_review_requests", PhysicianReviewRequest, None),
        ("trigger_result_evidence", TriggerResultEvidence, None),
        ("trigger_results", TriggerResult, None),
        ("finding_evidence", FindingEvidence, None),
        ("clinical_findings", ClinicalFinding, None),
        ("analysis_runs", AnalysisRun, None),
        ("rag_embedding_chunks", chunks, chunks.observation_id.not_in(keep_observations)),
        ("observation_embeddings", ObservationEmbedding, ObservationEmbedding.observation_id.not_in(keep_observations)),
        ("observations", Observation, Observation.id.not_in(keep_observations)),
        ("encounters", Encounter, Encounter.id.not_in(keep_encounters)),
    ]


def count_deletions(session: Session, ids: dict[str, set] | None = None) -> dict[str, int]:
    """Read-only: how many rows reset() would delete."""
    counts = {}
    for table, model, where in plan(ids if ids is not None else seed_ids()):
        query = select(func.count()).select_from(model)
        counts[table] = session.scalar(query if where is None else query.where(where))
    return counts


def reset(session: Session) -> dict[str, int]:
    """Delete demo-created rows and re-run the seeds. The caller owns the transaction."""
    ids = seed_ids()
    counts = {}
    for table, model, where in plan(ids):
        statement = delete(model) if where is None else delete(model).where(where)
        counts[table] = session.execute(statement.execution_options(synchronize_session=False)).rowcount
    for function in _seed_functions():
        function(session)
    session.flush()
    return counts


def _print(counts: dict[str, int], heading: str) -> None:
    print(heading)
    for table, number in counts.items():
        print(f"  {table:<26} {number}")
    print(f"  {'total':<26} {sum(counts.values())}")


def main(argv: list[str] | None = None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(description="Reset the LOCAL demo database to its seeded starting state.")
    parser.add_argument("--yes", action="store_true", help="Actually delete. Without it, only show what would be deleted.")
    args = parser.parse_args(argv)

    settings = get_settings()
    require_local_host(settings.postgres_host)  # before any connection or deletion

    if session_factory is None:  # tests inject a session bound to the disposable test database
        from app.db.session import get_engine
        session_factory = lambda: Session(get_engine())  # noqa: E731
    with session_factory() as session:
        if not args.yes:
            counts = count_deletions(session)  # SELECTs only
            session.rollback()
            _print(counts, f"Dry run on {settings.postgres_host}/{settings.postgres_db}: nothing deleted. Would delete:")
            print("Re-run with --yes to reset.", file=sys.stderr)
            return 1
        with session.begin():
            counts = reset(session)
    _print(counts, f"Demo database reset on {settings.postgres_host}/{settings.postgres_db}. Deleted:")
    print("Seed data restored. Reload the browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
