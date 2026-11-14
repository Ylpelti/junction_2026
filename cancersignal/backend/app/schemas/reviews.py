from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.analysis import AnalysisResponse
from app.schemas.records import NonEmpty, PatientRead, Record


class ReviewRequestCreate(Record):
    analysis_id: UUID
    # Demo display identity only; not authenticated or an authorization claim.
    submitted_by: NonEmpty | None = Field(default=None, max_length=120)


class ReviewRequestRead(Record):
    id: UUID
    patient_id: UUID
    analysis_id: UUID
    status: Literal["pending", "reviewed"]
    priority: Literal["urgent", "review", "normal"]
    created_at: AwareDatetime
    submitted_by: str | None


class ReviewRequestResponse(ReviewRequestRead):
    # Existing contracts reused at read time; no duplicated analysis JSON in storage.
    patient: PatientRead
    analysis: AnalysisResponse
