from pydantic import Field, model_validator
from uuid import UUID

from app.contracts.common import Contract
from app.schemas.records import NonEmpty, Record


class EvidenceReference(Record):
    # Shared primitive, re-exported at its original API import path.
    observation_id: UUID
    source_excerpt: NonEmpty | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.start_offset is None and self.end_offset is None:
            return self
        if (self.start_offset is None or self.end_offset is None
                or self.end_offset <= self.start_offset or self.source_excerpt is None):
            raise ValueError("Offsets require an excerpt and a nonempty [start, end) range.")
        return self


class SourceReference(EvidenceReference, Contract):
    """Immutable internal reference with the same fields as public evidence."""
