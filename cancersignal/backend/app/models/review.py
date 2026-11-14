"""Human-requested review handoffs; no physician decisions or referral records."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.records import AnalysisRun, Patient


class PhysicianReviewRequest(Base):
    __tablename__ = "physician_review_requests"
    __table_args__ = (
        ForeignKeyConstraint(["analysis_id", "patient_id"], ["analysis_runs.id", "analysis_runs.patient_id"]),
        UniqueConstraint("analysis_id", name="uq_physician_review_analysis"),
        CheckConstraint("status = 'pending'", name="review_status"),
        CheckConstraint("priority IN ('urgent', 'review', 'normal')", name="review_priority"),
        CheckConstraint("submitted_by IS NULL OR length(trim(submitted_by)) > 0", name="review_submitter"),
        Index("ix_physician_review_queue", "status", "created_at", "id"),
        Index("ix_physician_review_patient", "patient_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    analysis_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default=text("'pending'"))
    # Server-derived snapshot of saved rule results, never an accepted request field.
    priority: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_by: Mapped[str | None] = mapped_column(String(120))

    patient: Mapped[Patient] = relationship(viewonly=True)
    analysis_run: Mapped[AnalysisRun] = relationship(viewonly=True)
