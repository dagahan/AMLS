from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin

if TYPE_CHECKING:
    from src.models.alchemy.entrance_test import EntranceTestSession
    from src.models.alchemy.problem import Problem, ProblemAnswerOption
    from src.models.alchemy.user import User


class ResponseEvent(Base, IdMixin):
    __tablename__ = "responses"

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
    answer_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problem_answer_options.id", ondelete="SET NULL"),
        nullable=True,
    )
    entrance_test_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entrance_test_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()
    problem: Mapped["Problem"] = relationship()
    answer_option: Mapped["ProblemAnswerOption | None"] = relationship()
    entrance_test_session: Mapped["EntranceTestSession | None"] = relationship()
