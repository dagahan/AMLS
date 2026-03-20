from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.difficulty import Difficulty
    from src.models.alchemy.problem_type import ProblemType
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
    problem_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    condition_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    solution_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    subtopic: Mapped["Subtopic"] = relationship(back_populates="problems")
    difficulty: Mapped["Difficulty"] = relationship(back_populates="problems")
    problem_type: Mapped["ProblemType"] = relationship(back_populates="problems")
    answer_options: Mapped[list["ProblemAnswerOption"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        order_by="ProblemAnswerOption.id",
    )


class ProblemAnswerOption(Base, IdMixin):
    __tablename__ = "problem_answer_options"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    problem: Mapped["Problem"] = relationship(back_populates="answer_options")
