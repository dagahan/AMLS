from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index
from sqlalchemy import PrimaryKeyConstraint, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.enums import UserRole


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=UserRole.STUDENT,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    solved_problems: Mapped[list["UserSolvedProblem"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    failed_problems: Mapped[list["UserFailedProblem"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Topic(Base, IdMixin, TimestampMixin):
    __tablename__ = "topics"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    subtopics: Mapped[list["Subtopic"]] = relationship(
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

    topic: Mapped[Topic] = relationship(back_populates="subtopics")
    problems: Mapped[list["Problem"]] = relationship(back_populates="subtopic")


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

    skill: Mapped[Skill] = relationship(back_populates="subskills")
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


class Difficulty(Base, IdMixin, TimestampMixin):
    __tablename__ = "difficulties"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    coefficient: Mapped[float] = mapped_column(Float, nullable=False)

    problems: Mapped[list["Problem"]] = relationship(back_populates="difficulty")


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
    condition_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    solution_images: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    subtopic: Mapped[Subtopic] = relationship(back_populates="problems")
    difficulty: Mapped[Difficulty] = relationship(back_populates="problems")
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

    problem: Mapped[Problem] = relationship(back_populates="subskill_links")
    subskill: Mapped[Subskill] = relationship(back_populates="problem_links")


class ProblemAnswerOption(Base, IdMixin):
    __tablename__ = "problem_answer_options"
    __table_args__ = (
        Index(
            "uq_problem_correct_answer",
            "problem_id",
            unique=True,
            postgresql_where=text("is_correct = true"),
        ),
    )

    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    problem: Mapped[Problem] = relationship(back_populates="answer_options")


class UserSolvedProblem(Base):
    __tablename__ = "user_solved_problems"
    __table_args__ = (PrimaryKeyConstraint("user_id", "problem_id", name="pk_user_solved_problem"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="solved_problems")
    problem: Mapped[Problem] = relationship()


class UserFailedProblem(Base):
    __tablename__ = "user_failed_problems"
    __table_args__ = (PrimaryKeyConstraint("user_id", "problem_id", name="pk_user_failed_problem"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="failed_problems")
    problem: Mapped[Problem] = relationship()
