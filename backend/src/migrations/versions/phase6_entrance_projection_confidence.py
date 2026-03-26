"""phase6 entrance projection confidence rollout

Revision ID: phase6_projection_confidence
Revises: phase5_entrance_bayes
Create Date: 2026-03-25 18:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "phase6_projection_confidence"
down_revision: str | None = "phase5_entrance_bayes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE entrance_test_sessions
            SET
                final_state_probability = NULL,
                updated_at = now()
            WHERE status = 'completed'
              AND final_state_index IS NOT NULL
              AND final_state_probability IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    return None
