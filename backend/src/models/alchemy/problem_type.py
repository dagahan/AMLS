from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.problem import Problem


class ProblemType(Base, IdMixin, TimestampMixin):
    __tablename__ = "problem_types"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    problems: Mapped[list["Problem"]] = relationship(back_populates="problem_type")
    prerequisite_links: Mapped[list["ProblemTypePrerequisite"]] = relationship(
        back_populates="problem_type",
        cascade="all, delete-orphan",
        foreign_keys="ProblemTypePrerequisite.problem_type_id",
    )
    dependent_links: Mapped[list["ProblemTypePrerequisite"]] = relationship(
        back_populates="prerequisite_problem_type",
        foreign_keys="ProblemTypePrerequisite.prerequisite_problem_type_id",
    )


class ProblemTypePrerequisite(Base):
    __tablename__ = "problem_type_prerequisites"
    __table_args__ = (
        PrimaryKeyConstraint(
            "problem_type_id",
            "prerequisite_problem_type_id",
            name="pk_problem_type_prerequisites",
        ),
        CheckConstraint(
            "problem_type_id <> prerequisite_problem_type_id",
            name="ck_problem_type_prerequisite_not_self",
        ),
    )

    problem_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    prerequisite_problem_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_types.id", ondelete="CASCADE"),
        nullable=False,
    )

    problem_type: Mapped["ProblemType"] = relationship(
        back_populates="prerequisite_links",
        foreign_keys=[problem_type_id],
    )
    prerequisite_problem_type: Mapped["ProblemType"] = relationship(
        back_populates="dependent_links",
        foreign_keys=[prerequisite_problem_type_id],
    )
