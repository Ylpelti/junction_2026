from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue

from app.schemas.records import Record


class ModelPrediction(Record):
    """Existing prediction shape, shared without promoting predictions to facts."""
    patient_id: UUID
    model_name: str
    model_version: str
    as_of: AwareDatetime
    prediction_type: str
    value: JsonValue
    evidence_observation_ids: list[UUID] = Field(default_factory=list)
    uncertainty: str | None = None
