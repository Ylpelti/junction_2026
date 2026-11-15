"""PostgreSQL access, scoped by patient and both time axes before ranking."""
import re
from decimal import Decimal

from sqlalchemy import String, case, cast, func, literal_column, or_, select

from app.contracts.clinical_context import SourceObservation, StructuredPatientContext
from app.contracts.common import ComponentProvenance, Coverage
from app.models import Observation, Patient
from app.rag.storage import EmbeddingChunk


def scoped_observations(scope):
    query = select(Observation).where(Observation.patient_id == scope.patient_id,
        Observation.observed_at < scope.as_of, Observation.recorded_at < scope.recorded_before)
    if scope.observed_since is not None:
        query = query.where(Observation.observed_at >= scope.observed_since)
    return query


class PatientNotFound(ValueError):
    pass


class PatientRepository:
    def __init__(self, session):
        self.session = session

    def sources(self, scope):
        if self.session.get(Patient, scope.patient_id) is None:
            raise PatientNotFound("Synthetic patient does not exist.")
        return tuple(SourceObservation.model_validate(row) for row in self.session.scalars(
            scoped_observations(scope).order_by(Observation.observed_at, Observation.recorded_at, Observation.id)))

    def lexical_scores(self, scope, query):
        # Only letters/numbers reach tsquery syntax; values remain bound parameters.
        terms = list(dict.fromkeys(re.findall(r"[^\W_]+", query.casefold())))[:64]
        if not terms:
            return {}
        eligible = scoped_observations(scope).cte("eligible_lexical_history")
        document = (func.coalesce(eligible.c.text, "") + " " + func.coalesce(eligible.c.code, "")
                    + " " + func.coalesce(cast(eligible.c.numeric_value, String), "")
                    + " " + func.coalesce(eligible.c.unit, ""))
        expression = " | ".join(terms)
        scores = []
        for language in ("english", "simple"):
            configuration = literal_column(f"'{language}'::regconfig")
            scores.append(func.ts_rank_cd(func.to_tsvector(configuration, document),
                                         func.to_tsquery(configuration, expression)))
        numeric_terms = [Decimal(value.replace(",", ".")) for value in
                         re.findall(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?(?!\w)", query)[:64]]
        exact_numeric = case((eligible.c.numeric_value.in_(numeric_terms), 1.0), else_=0.0) if numeric_terms else 0.0
        score = (scores[0] + scores[1] + exact_numeric).label("score")
        return {row.id: float(row.score) for row in self.session.execute(
            select(eligible.c.id, score).where(score > 0))}

    def dense_chunks(self, scope, vector, model_key):
        eligible = scoped_observations(scope).cte("eligible_dense_history")
        distance = EmbeddingChunk.embedding.cosine_distance(vector).label("distance")
        return self.session.execute(select(EmbeddingChunk.observation_id, EmbeddingChunk.source_digest,
            EmbeddingChunk.start_offset, EmbeddingChunk.end_offset, distance)
            .join(eligible, eligible.c.id == EmbeddingChunk.observation_id)
            .where(EmbeddingChunk.model_key == model_key)
            .order_by(distance, EmbeddingChunk.observation_id, EmbeddingChunk.chunk_index)).all()

    def structured(self, *, scope, codes=None):
        if codes is not None and not codes:
            raise ValueError("Use None to request all codes.")
        if self.session.get(Patient, scope.patient_id) is None:
            raise PatientNotFound("Synthetic patient does not exist.")
        query = scoped_observations(scope).where(or_(Observation.observation_type.in_(("laboratory", "vital_sign")),
                                                    Observation.numeric_value.is_not(None)))
        if codes is not None:
            query = query.where(Observation.code.in_(codes))
        sources = tuple(SourceObservation.model_validate(row) for row in self.session.scalars(
            query.order_by(Observation.observed_at, Observation.id)))
        return StructuredPatientContext(patient_id=scope.patient_id, as_of=scope.as_of,
            observed_since=scope.observed_since, recorded_before=scope.recorded_before,
            observations=sources, requested_codes=codes, coverage=Coverage(status="complete", eligible_count=len(sources)),
            access=ComponentProvenance(name="postgres-patient-measurements", version="1.0", method="structured"))
