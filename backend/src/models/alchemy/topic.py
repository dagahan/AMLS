from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.problem import Problem


class Topic(Base, IdMixin, TimestampMixin):
    __tablename__ = "topics"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    subtopics: Mapped[list["Subtopic"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
    subtopic_links: Mapped[list["TopicSubtopic"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )


class Subtopic(Base, IdMixin, TimestampMixin):
    __tablename__ = "subtopics"
    __table_args__ = (UniqueConstraint("topic_id", "name", name="uq_subtopic_topic_name"),)

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    topic: Mapped["Topic"] = relationship(back_populates="subtopics")
    problems: Mapped[list["Problem"]] = relationship(back_populates="subtopic")
    topic_links: Mapped[list["TopicSubtopic"]] = relationship(
        back_populates="subtopic",
        cascade="all, delete-orphan",
    )


class TopicSubtopic(Base):
    __tablename__ = "topic_subtopics"
    __table_args__ = (
        PrimaryKeyConstraint("topic_id", "subtopic_id", name="pk_topic_subtopics"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_topic_subtopic_weight"),
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    subtopic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subtopics.id", ondelete="CASCADE"),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    topic: Mapped["Topic"] = relationship(back_populates="subtopic_links")
    subtopic: Mapped["Subtopic"] = relationship(back_populates="topic_links")


class SubtopicPrerequisite(Base, IdMixin):
    __tablename__ = "subtopic_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "subtopic_id",
            "prerequisite_subtopic_id",
            name="uq_subtopic_prerequisite_pair",
        ),
        CheckConstraint("mastery_weight >= 0 AND mastery_weight <= 1", name="ck_subtopic_weight"),
    )

    subtopic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subtopics.id", ondelete="CASCADE"),
        nullable=False,
    )
    prerequisite_subtopic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subtopics.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastery_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
