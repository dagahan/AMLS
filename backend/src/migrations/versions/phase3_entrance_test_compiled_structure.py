"""phase3 entrance test compiled structure

Revision ID: phase3_entrance_test_structure
Revises: phase2_entrance_result
Create Date: 2026-03-22 23:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase3_entrance_test_structure"
down_revision: str | None = "phase2_entrance_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    entrance_test_structure_status_enum = postgresql.ENUM(
        "ready",
        "failed",
        name="entrance_test_structure_status_enum",
        create_type=False,
    )
    entrance_test_structure_status_enum.create(bind, checkfirst=True)

    if not _has_table("entrance_test_structures"):
        op.create_table(
            "entrance_test_structures",
            sa.Column("structure_version", sa.Integer(), nullable=False),
            sa.Column("source_hash", sa.String(length=64), nullable=False),
            sa.Column("artifact_kind", sa.String(length=64), nullable=False),
            sa.Column("status", entrance_test_structure_status_enum, nullable=False),
            sa.Column("problem_type_count", sa.Integer(), nullable=False),
            sa.Column("edge_count", sa.Integer(), nullable=False),
            sa.Column("feasible_state_count", sa.BigInteger(), nullable=False),
            sa.Column("compiled_payload", postgresql.BYTEA(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("structure_version"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    entrance_test_structure_status_enum = postgresql.ENUM(
        "ready",
        "failed",
        name="entrance_test_structure_status_enum",
        create_type=False,
    )

    if _has_table("entrance_test_structures"):
        op.drop_table("entrance_test_structures")

    entrance_test_structure_status_enum.drop(bind, checkfirst=True)


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()
