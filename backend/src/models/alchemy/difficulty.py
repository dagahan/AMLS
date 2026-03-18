from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.alchemy.common import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from src.models.alchemy.problem import Problem


class Difficulty(Base, IdMixin, TimestampMixin):
    __tablename__ = "difficulties"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    coefficient: Mapped[float] = mapped_column(Float, nullable=False)

    problems: Mapped[list["Problem"]] = relationship(back_populates="difficulty")
