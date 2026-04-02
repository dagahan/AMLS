from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.course_graph import CourseGraphVersion, CourseNode
    from src.models.alchemy.user import User


class Course(Base, IdMixin, TimestampMixin):
    __tablename__ = "courses"

    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_graph_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_graph_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    author: Mapped["User"] = relationship(
        back_populates="courses_authored",
        foreign_keys=[author_id],
    )
    current_graph_version: Mapped["CourseGraphVersion | None"] = relationship(
        back_populates="published_for_course",
        foreign_keys=[current_graph_version_id],
        post_update=True,
    )
    graph_versions: Mapped[list["CourseGraphVersion"]] = relationship(
        back_populates="course",
        foreign_keys="CourseGraphVersion.course_id",
        cascade="all, delete-orphan",
    )
    nodes: Mapped[list["CourseNode"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )


class CourseEnrollment(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_course_enrollments_user_course"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="course_enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")
