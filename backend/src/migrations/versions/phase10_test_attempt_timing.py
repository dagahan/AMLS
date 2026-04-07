"""phase10 test attempt timing support

Revision ID: phase10_test_attempt_timing
Revises: phase9_final_diploma_features
Create Date: 2026-04-03 12:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "phase10_test_attempt_timing"
down_revision: str | None = "phase9_final_diploma_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "test_attempts",
        sa.Column(
            "total_paused_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.execute(
        """
        UPDATE test_attempts
        SET total_paused_seconds = 0
        WHERE total_paused_seconds IS NULL
        """
    )
    op.alter_column(
        "test_attempts",
        "total_paused_seconds",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("test_attempts", "total_paused_seconds")
