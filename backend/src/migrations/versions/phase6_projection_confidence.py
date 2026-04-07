"""phase6 projection confidence compatibility marker

Revision ID: phase6_projection_confidence
Revises: phase0_initial_schema
Create Date: 2026-04-03 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "phase6_projection_confidence"
down_revision: str | None = "phase0_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
