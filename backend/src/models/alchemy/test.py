from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin
from src.storage.db.enums import TestAttemptKind, TestAttemptStatus

__test__ = False

if TYPE_CHECKING:
    from src.models.alchemy.course_graph import CourseGraphVersion
    from src.models.alchemy.problem import Problem
    from src.models.alchemy.response import ResponseEvent
    from src.models.alchemy.user import User


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
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="test_attempts")
    graph_version: Mapped["CourseGraphVersion"] = relationship(back_populates="test_attempts")
    current_problem: Mapped["Problem | None"] = relationship()
    response_events: Mapped[list["ResponseEvent"]] = relationship(back_populates="test_attempt")
    graph_assessments: Mapped[list["GraphAssessment"]] = relationship(
        back_populates="source_test_attempt",
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assessment_kind: Mapped[TestAttemptKind] = mapped_column(
        Enum(
            TestAttemptKind,
            name="test_attempt_kind_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="graph_assessments")
    graph_version: Mapped["CourseGraphVersion"] = relationship(back_populates="graph_assessments")
    source_test_attempt: Mapped["TestAttempt"] = relationship(back_populates="graph_assessments")
