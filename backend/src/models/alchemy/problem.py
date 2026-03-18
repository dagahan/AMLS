from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.difficulty import Difficulty
    from src.models.alchemy.skill import Subskill
    from src.models.alchemy.topic import Subtopic


class Problem(Base, IdMixin, TimestampMixin):
    __tablename__ = "problems"

    subtopic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subtopics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    difficulty_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("difficulties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    right_answer: Mapped[str] = mapped_column(Text, nullable=False)
    condition_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    solution_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    subtopic: Mapped["Subtopic"] = relationship(back_populates="problems")
    difficulty: Mapped["Difficulty"] = relationship(back_populates="problems")
    answer_options: Mapped[list["ProblemAnswerOption"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        order_by="ProblemAnswerOption.id",
    )
    subskill_links: Mapped[list["ProblemSubskill"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
    )


class ProblemSubskill(Base):
    __tablename__ = "problem_subskills"
    __table_args__ = (
        PrimaryKeyConstraint("problem_id", "subskill_id", name="pk_problem_subskills"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_problem_subskill_weight"),
    )

    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    subskill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subskills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    problem: Mapped["Problem"] = relationship(back_populates="subskill_links")
    subskill: Mapped["Subskill"] = relationship(back_populates="problem_links")


class ProblemAnswerOption(Base, IdMixin):
    __tablename__ = "problem_answer_options"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    problem: Mapped["Problem"] = relationship(back_populates="answer_options")
