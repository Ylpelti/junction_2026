from datetime import datetime
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Observation
from app.rag.context import ContextObservation, RetrievedContext
from app.schemas.records import ObservationRead


def retrieve_context(patient_id: UUID, query: str, db_session: Session, *, before: datetime) -> RetrievedContext:
    """Retrieve all eligible prototype history, then rank lexical overlap.

    No embeddings are available in the fixture. Keeping the full eligible history
    avoids hiding later negation/resolution behind a ranked top-k cutoff.
    """
    records = db_session.scalars(select(Observation).where(
        Observation.patient_id == patient_id,
        Observation.observed_at < before,
        Observation.recorded_at < before,
    ).order_by(Observation.observed_at, Observation.recorded_at, Observation.id)).all()
    terms = set(re.findall(r"\w+", query.casefold()))

    def relevance(record):
        words = set(re.findall(r"\w+", f"{record.text or ''} {record.code or ''}".casefold()))
        return (len(terms & words), record.observed_at, str(record.id))

    ranked = sorted(records, key=relevance, reverse=True)
    return RetrievedContext(patient_id=patient_id, cutoff=before,
        observations=[ContextObservation(observation=ObservationRead.model_validate(row),
                     source_excerpt=row.text) for row in records],
        ranked_observation_ids=[row.id for row in ranked])
