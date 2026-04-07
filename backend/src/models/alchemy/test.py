from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin
from src.storage.db.enums import (
    GraphAssessmentReviewStatus,
    TestAttemptKind,
    TestAttemptStatus,
)

__test__ = False

if TYPE_CHECKING:
    from src.models.alchemy.course_graph import CourseGraphVersion
    from src.models.alchemy.problem import Problem
    from src.models.alchemy.response import ResponseEvent
    from src.models.alchemy.user import User


def calculate_elapsed_solve_seconds(
    *,
    status: TestAttemptStatus,
    started_at: datetime | None,
    paused_at: datetime | None,
    ended_at: datetime | None,
    total_paused_seconds: int,
) -> int:
    if started_at is None:
        return 0

    if status == TestAttemptStatus.ACTIVE:
        reference_time = datetime.now(UTC)
    elif paused_at is not None:
        reference_time = paused_at
    elif ended_at is not None:
        reference_time = ended_at
    else:
        reference_time = datetime.now(UTC)

    elapsed_seconds = int((reference_time - started_at).total_seconds()) - total_paused_seconds
    return max(0, elapsed_seconds)


class TestAttempt(Base, IdMixin, TimestampMixin):
    __tablename__ = "test_attempts"
    __table_args__ = (
        Index(
            "uq_test_attempts_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    graph_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_graph_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[TestAttemptKind] = mapped_column(
        Enum(
            TestAttemptKind,
            name="test_attempt_kind_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    status: Mapped[TestAttemptStatus] = mapped_column(
        Enum(
            TestAttemptStatus,
            name="test_attempt_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    current_problem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
    )
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_paused_seconds: Mapped[int] = mapped_column(default=0, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="test_attempts")
    graph_version: Mapped["CourseGraphVersion"] = relationship(back_populates="test_attempts")
    current_problem: Mapped["Problem | None"] = relationship()
    response_events: Mapped[list["ResponseEvent"]] = relationship(back_populates="test_attempt")
    graph_assessments: Mapped[list["GraphAssessment"]] = relationship(
        back_populates="source_test_attempt",
    )


    @property
    def elapsed_solve_seconds(self) -> int:
        return calculate_elapsed_solve_seconds(
            status=self.status,
            started_at=self.started_at,
            paused_at=self.paused_at,
            ended_at=self.ended_at,
            total_paused_seconds=self.total_paused_seconds,
        )


class GraphAssessment(Base, IdMixin, TimestampMixin):
    __tablename__ = "graph_assessments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    graph_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_graph_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_test_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_attempts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    state: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    state_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    assessment_kind: Mapped[TestAttemptKind] = mapped_column(
        Enum(
            TestAttemptKind,
            name="test_attempt_kind_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    review_status: Mapped[GraphAssessmentReviewStatus] = mapped_column(
        Enum(
            GraphAssessmentReviewStatus,
            name="graph_assessment_review_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=GraphAssessmentReviewStatus.PENDING,
        nullable=False,
    )
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_recommendations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    review_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="graph_assessments")
    graph_version: Mapped["CourseGraphVersion"] = relationship(back_populates="graph_assessments")
    source_test_attempt: Mapped["TestAttempt"] = relationship(back_populates="graph_assessments")
