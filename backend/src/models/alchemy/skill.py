from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.problem import ProblemSubskill


class Skill(Base, IdMixin, TimestampMixin):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    subskills: Mapped[list["Subskill"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class Subskill(Base, IdMixin, TimestampMixin):
    __tablename__ = "subskills"
    __table_args__ = (UniqueConstraint("skill_id", "name", name="uq_subskill_skill_name"),)

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    skill: Mapped["Skill"] = relationship(back_populates="subskills")
    problem_links: Mapped[list["ProblemSubskill"]] = relationship(back_populates="subskill")


class SubskillPrerequisite(Base, IdMixin):
    __tablename__ = "subskill_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "subskill_id",
            "prerequisite_subskill_id",
            name="uq_subskill_prerequisite_pair",
        ),
        CheckConstraint("mastery_weight >= 0 AND mastery_weight <= 1", name="ck_subskill_weight"),
    )

    subskill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subskills.id", ondelete="CASCADE"),
        nullable=False,
    )
    prerequisite_subskill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subskills.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastery_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
