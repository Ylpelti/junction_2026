from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field
from app.schemas.records import NonEmpty, Record


class WorkflowCreate(Record):
    actor: NonEmpty = Field(max_length=120)
    comment: NonEmpty | None = Field(default=None, max_length=4000)


class DismissalCreate(WorkflowCreate):
    patient_id: UUID
    reason_code: Literal["already_aware", "another_diagnosis", "patient_declined", "other"]


class DismissalRead(DismissalCreate):
    id: UUID
    analysis_id: UUID
    created_at: AwareDatetime


class DecisionCreate(WorkflowCreate):
    action: Literal["fit_ordered", "referral_made", "no_action", "acknowledged"]


class DecisionRead(DecisionCreate):
    id: UUID
    review_request_id: UUID
    status: Literal["reviewed"]
    created_at: AwareDatetime
