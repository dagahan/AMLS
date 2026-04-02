from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin
from src.storage.db.enums import CourseGraphVersionStatus

if TYPE_CHECKING:
    from src.models.alchemy.course import Course
    from src.models.alchemy.problem import Problem
    from src.models.alchemy.problem_type import ProblemType
    from src.models.alchemy.test import GraphAssessment, TestAttempt


class CourseNode(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_nodes"
    __table_args__ = (
        UniqueConstraint("course_id", "name", name="uq_course_nodes_course_name"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped["Course"] = relationship(back_populates="nodes")
    problem_type: Mapped["ProblemType | None"] = relationship()
    lectures: Mapped[list["Lecture"]] = relationship(
        back_populates="course_node",
        cascade="all, delete-orphan",
    )
    graph_version_nodes: Mapped[list["CourseGraphVersionNode"]] = relationship(
        back_populates="course_node",
        cascade="all, delete-orphan",
    )
    prerequisite_edges: Mapped[list["CourseGraphVersionEdge"]] = relationship(
        back_populates="prerequisite_course_node",
        foreign_keys="CourseGraphVersionEdge.prerequisite_course_node_id",
    )
    dependent_edges: Mapped[list["CourseGraphVersionEdge"]] = relationship(
        back_populates="dependent_course_node",
        foreign_keys="CourseGraphVersionEdge.dependent_course_node_id",
    )
    problems: Mapped[list["Problem"]] = relationship(back_populates="course_node")


class CourseGraphVersion(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_graph_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version_number", name="uq_course_graph_versions_course_version"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CourseGraphVersionStatus] = mapped_column(
        Enum(
            CourseGraphVersionStatus,
            name="course_graph_version_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=CourseGraphVersionStatus.DRAFT,
        nullable=False,
    )
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped["Course"] = relationship(
        back_populates="graph_versions",
        foreign_keys=[course_id],
    )
    published_for_course: Mapped["Course | None"] = relationship(
        back_populates="current_graph_version",
        foreign_keys="Course.current_graph_version_id",
        viewonly=True,
        uselist=False,
    )
    version_nodes: Mapped[list["CourseGraphVersionNode"]] = relationship(
        back_populates="graph_version",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["CourseGraphVersionEdge"]] = relationship(
        back_populates="graph_version",
        cascade="all, delete-orphan",
    )
    test_attempts: Mapped[list["TestAttempt"]] = relationship(back_populates="graph_version")
    graph_assessments: Mapped[list["GraphAssessment"]] = relationship(back_populates="graph_version")


class Lecture(Base, IdMixin, TimestampMixin):
    __tablename__ = "lectures"

    course_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    course_node: Mapped["CourseNode"] = relationship(back_populates="lectures")
    pages: Mapped[list["LecturePage"]] = relationship(
        back_populates="lecture",
        cascade="all, delete-orphan",
        order_by="LecturePage.page_number",
    )
    graph_version_nodes: Mapped[list["CourseGraphVersionNode"]] = relationship(
        back_populates="lecture",
    )


class CourseGraphVersionNode(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_graph_version_nodes"
    __table_args__ = (
        UniqueConstraint(
            "graph_version_id",
            "course_node_id",
            name="uq_course_graph_version_nodes_membership",
        ),
    )

    graph_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_graph_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    lecture_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lectures.id", ondelete="SET NULL"),
        nullable=True,
    )
    topological_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    graph_version: Mapped["CourseGraphVersion"] = relationship(back_populates="version_nodes")
    course_node: Mapped["CourseNode"] = relationship(back_populates="graph_version_nodes")
    lecture: Mapped["Lecture | None"] = relationship(back_populates="graph_version_nodes")


class CourseGraphVersionEdge(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_graph_version_edges"
    __table_args__ = (
        UniqueConstraint(
            "graph_version_id",
            "prerequisite_course_node_id",
            "dependent_course_node_id",
            name="uq_course_graph_version_edges_membership",
        ),
        CheckConstraint(
            "prerequisite_course_node_id <> dependent_course_node_id",
            name="ck_course_graph_version_edge_not_self",
        ),
    )

    graph_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_graph_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    prerequisite_course_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    dependent_course_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )

    graph_version: Mapped["CourseGraphVersion"] = relationship(back_populates="edges")
    prerequisite_course_node: Mapped["CourseNode"] = relationship(
        back_populates="prerequisite_edges",
        foreign_keys=[prerequisite_course_node_id],
    )
    dependent_course_node: Mapped["CourseNode"] = relationship(
        back_populates="dependent_edges",
        foreign_keys=[dependent_course_node_id],
    )


class LecturePage(Base, IdMixin, TimestampMixin):
    __tablename__ = "lecture_pages"
    __table_args__ = (
        UniqueConstraint("lecture_id", "page_number", name="uq_lecture_pages_lecture_page_number"),
    )

    lecture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lectures.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_content: Mapped[str] = mapped_column(Text, nullable=False)

    lecture: Mapped["Lecture"] = relationship(back_populates="pages")
