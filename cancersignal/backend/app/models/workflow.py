"""Append-only through the API; one final action per analysis/request."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AlertDismissal(Base):
    __tablename__ = "alert_dismissals"
    __table_args__ = (
        ForeignKeyConstraint(["analysis_id", "patient_id"], ["analysis_runs.id", "analysis_runs.patient_id"]),
        UniqueConstraint("analysis_id"),
        CheckConstraint("reason_code IN ('already_aware', 'another_diagnosis', 'patient_declined', 'other')", name="dismissal_reason"),
        CheckConstraint("length(trim(actor)) > 0", name="dismissal_actor"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    reason_code: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(String(4000))
    actor: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhysicianDecision(Base):
    __tablename__ = "physician_decisions"
    __table_args__ = (
        UniqueConstraint("review_request_id"),
        CheckConstraint("action IN ('fit_ordered', 'referral_made', 'no_action', 'acknowledged')", name="decision_action"),
        CheckConstraint("status = 'reviewed'", name="decision_status"),
        CheckConstraint("length(trim(actor)) > 0", name="decision_actor"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    review_request_id: Mapped[UUID] = mapped_column(ForeignKey("physician_review_requests.id"))
    action: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(String(4000))
    actor: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="reviewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
