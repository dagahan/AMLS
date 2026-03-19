from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint
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
    subskill_links: Mapped[list["SkillSubskill"]] = relationship(
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
    skill_links: Mapped[list["SkillSubskill"]] = relationship(
        back_populates="subskill",
        cascade="all, delete-orphan",
    )


class SkillSubskill(Base):
    __tablename__ = "skill_subskills"
    __table_args__ = (
        PrimaryKeyConstraint("skill_id", "subskill_id", name="pk_skill_subskills"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_skill_subskill_weight"),
    )

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    subskill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subskills.id", ondelete="CASCADE"),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    skill: Mapped["Skill"] = relationship(back_populates="subskill_links")
    subskill: Mapped["Subskill"] = relationship(back_populates="skill_links")


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
