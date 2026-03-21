from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.enums import EntranceTestStatus
from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.problem import Problem
    from src.models.alchemy.user import User


class EntranceTestSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "entrance_test_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[EntranceTestStatus] = mapped_column(
        Enum(
            EntranceTestStatus,
            name="entrance_test_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=EntranceTestStatus.PENDING,
        nullable=False,
    )
    structure_version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
    )
    current_problem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="entrance_test_session")
    current_problem: Mapped["Problem | None"] = relationship()
