"""phase2 entrance test result persistence

Revision ID: phase2_entrance_result
Revises: phase1_entrance_refactor
Create Date: 2026-03-22 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase2_entrance_result"
down_revision: str | None = "phase1_entrance_refactor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not _has_column("entrance_test_sessions", "final_state_index"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column("final_state_index", sa.Integer(), nullable=True),
        )

    if not _has_column("entrance_test_sessions", "final_state_probability"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column("final_state_probability", sa.Float(), nullable=True),
        )

    if not _has_column("entrance_test_sessions", "learned_problem_type_ids"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column(
                "learned_problem_type_ids",
                postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                nullable=False,
                server_default=sa.text("'{}'::uuid[]"),
            ),
        )
        op.alter_column(
            "entrance_test_sessions",
            "learned_problem_type_ids",
            server_default=None,
        )

    if not _has_column("entrance_test_sessions", "inner_fringe_problem_type_ids"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column(
                "inner_fringe_problem_type_ids",
                postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                nullable=False,
                server_default=sa.text("'{}'::uuid[]"),
            ),
        )
        op.alter_column(
            "entrance_test_sessions",
            "inner_fringe_problem_type_ids",
            server_default=None,
        )

    if not _has_column("entrance_test_sessions", "outer_fringe_problem_type_ids"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column(
                "outer_fringe_problem_type_ids",
                postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                nullable=False,
                server_default=sa.text("'{}'::uuid[]"),
            ),
        )
        op.alter_column(
            "entrance_test_sessions",
            "outer_fringe_problem_type_ids",
            server_default=None,
        )


def downgrade() -> None:
    if _has_column("entrance_test_sessions", "outer_fringe_problem_type_ids"):
        op.drop_column("entrance_test_sessions", "outer_fringe_problem_type_ids")

    if _has_column("entrance_test_sessions", "inner_fringe_problem_type_ids"):
        op.drop_column("entrance_test_sessions", "inner_fringe_problem_type_ids")

    if _has_column("entrance_test_sessions", "learned_problem_type_ids"):
        op.drop_column("entrance_test_sessions", "learned_problem_type_ids")

    if _has_column("entrance_test_sessions", "final_state_probability"):
        op.drop_column("entrance_test_sessions", "final_state_probability")

    if _has_column("entrance_test_sessions", "final_state_index"):
        op.drop_column("entrance_test_sessions", "final_state_index")


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)
