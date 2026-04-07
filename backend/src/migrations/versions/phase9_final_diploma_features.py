"""phase9 final diploma feature schema

Revision ID: phase9_final_diploma_features
Revises: phase7_course_dag_assessment
Create Date: 2026-04-03 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase9_final_diploma_features"
down_revision: str | None = "phase7_course_dag_assessment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("ALTER TYPE test_attempt_kind_enum ADD VALUE IF NOT EXISTS 'exam'")
    op.execute("ALTER TYPE test_attempt_kind_enum ADD VALUE IF NOT EXISTS 'mistakes'")

    graph_assessment_review_status_enum = postgresql.ENUM(
        "pending",
        "succeeded",
        "failed",
        name="graph_assessment_review_status_enum",
        create_type=False,
    )
    graph_assessment_review_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "responses",
        sa.Column(
            "revealed_solution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "graph_assessments",
        sa.Column(
            "review_status",
            graph_assessment_review_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "graph_assessments",
        sa.Column("review_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "graph_assessments",
        sa.Column(
            "review_recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "graph_assessments",
        sa.Column("review_model", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "graph_assessments",
        sa.Column("review_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "graph_assessments",
        sa.Column("review_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    graph_assessment_review_status_enum = postgresql.ENUM(
        "pending",
        "succeeded",
        "failed",
        name="graph_assessment_review_status_enum",
        create_type=False,
    )

    op.drop_column("graph_assessments", "review_generated_at")
    op.drop_column("graph_assessments", "review_error")
    op.drop_column("graph_assessments", "review_model")
    op.drop_column("graph_assessments", "review_recommendations")
    op.drop_column("graph_assessments", "review_text")
    op.drop_column("graph_assessments", "review_status")
    op.drop_column("responses", "revealed_solution")

    graph_assessment_review_status_enum.drop(bind, checkfirst=True)
