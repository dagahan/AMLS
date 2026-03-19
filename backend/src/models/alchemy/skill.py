from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.problem import ProblemSkill


class Skill(Base, IdMixin, TimestampMixin):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    problem_links: Mapped[list["ProblemSkill"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class SkillPrerequisite(Base, IdMixin):
    __tablename__ = "skill_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "skill_id",
            "prerequisite_skill_id",
            name="uq_skill_prerequisite_pair",
        ),
        CheckConstraint("mastery_weight >= 0 AND mastery_weight <= 1", name="ck_skill_weight"),
    )

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    prerequisite_skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastery_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
