"""phase5 entrance assessment bayesian engine rollout

Revision ID: phase5_entrance_bayes
Revises: phase4_config_difficulty
Create Date: 2026-03-23 18:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "phase5_entrance_bayes"
down_revision: str | None = "phase4_config_difficulty"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    incomplete_session_ids = bind.execute(
        sa.text(
            """
            SELECT id
            FROM entrance_test_sessions
            WHERE status IN ('pending', 'active')
            """
        )
    ).scalars().all()

    if incomplete_session_ids:
        delete_statement = sa.text(
            """
            DELETE FROM responses
            WHERE entrance_test_session_id IN :session_ids
            """
        ).bindparams(sa.bindparam("session_ids", expanding=True))
        bind.execute(delete_statement, {"session_ids": incomplete_session_ids})

    bind.execute(
        sa.text(
            """
            UPDATE entrance_test_sessions
            SET
                status = 'pending',
                structure_version = 1,
                current_problem_id = NULL,
                final_state_index = NULL,
                final_state_probability = NULL,
                learned_problem_type_ids = ARRAY[]::uuid[],
                inner_fringe_problem_type_ids = ARRAY[]::uuid[],
                outer_fringe_problem_type_ids = ARRAY[]::uuid[],
                business_config_snapshot = NULL,
                started_at = NULL,
                completed_at = NULL,
                skipped_at = NULL,
                updated_at = now()
            WHERE status IN ('pending', 'active')
            """
        )
    )


def downgrade() -> None:
    return None
