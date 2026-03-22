from __future__ import annotations

from sqlalchemy import BigInteger, Enum, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.enums import EntranceTestStructureStatus
from src.models.alchemy.common import Base, IdMixin, TimestampMixin


class EntranceTestStructure(Base, IdMixin, TimestampMixin):
    __tablename__ = "entrance_test_structures"

    structure_version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EntranceTestStructureStatus] = mapped_column(
        Enum(
            EntranceTestStructureStatus,
            name="entrance_test_structure_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    problem_type_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feasible_state_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    compiled_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
