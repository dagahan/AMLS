from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.storage.db.enums import DifficultyLevel, ProblemAnswerOptionType
from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.course_graph import CourseNode
    from src.models.alchemy.problem_type import ProblemType
    from src.models.alchemy.topic import Subtopic


class Problem(Base, IdMixin, TimestampMixin):
    __tablename__ = "problems"

    subtopic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subtopics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        Enum(
            DifficultyLevel,
            name="difficulty_level_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    problem_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    course_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    condition_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    solution_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    subtopic: Mapped["Subtopic"] = relationship(back_populates="problems")
    problem_type: Mapped["ProblemType"] = relationship(back_populates="problems")
    course_node: Mapped["CourseNode | None"] = relationship(back_populates="problems")
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
    type: Mapped[ProblemAnswerOptionType] = mapped_column(
        Enum(
            ProblemAnswerOptionType,
            name="problem_answer_option_type_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )

    problem: Mapped["Problem"] = relationship(back_populates="answer_options")
