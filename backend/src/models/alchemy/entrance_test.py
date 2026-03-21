from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.enums import EntranceTestStatus
from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
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
    problem_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        default=list,
        nullable=False,
    )
    response_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        default=list,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="entrance_test_session")
