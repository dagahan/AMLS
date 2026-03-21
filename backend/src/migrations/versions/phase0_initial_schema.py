"""phase0 initial schema

Revision ID: phase0_initial_schema
Revises: 
Create Date: 2026-03-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase0_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role_enum = postgresql.ENUM(
        "admin",
        "student",
        name="user_role_enum",
        create_type=False,
    )
    entrance_test_status_enum = postgresql.ENUM(
        "pending",
        "active",
        "completed",
        "skipped",
        name="entrance_test_status_enum",
        create_type=False,
    )
    problem_answer_option_type_enum = postgresql.ENUM(
        "right",
        "wrong",
        "i_dont_know",
        name="problem_answer_option_type_enum",
        create_type=False,
    )

    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)
    entrance_test_status_enum.create(bind, checkfirst=True)
    problem_answer_option_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "topics",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "difficulties",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("coefficient", sa.Float(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "problem_types",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "subtopics",
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "name", name="uq_subtopic_topic_name"),
    )

    op.create_table(
        "entrance_test_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", entrance_test_status_enum, nullable=False),
        sa.Column("problem_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("response_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "topic_subtopics",
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subtopic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_topic_subtopic_weight"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("topic_id", "subtopic_id", name="pk_topic_subtopics"),
    )

    op.create_table(
        "subtopic_prerequisites",
        sa.Column("subtopic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prerequisite_subtopic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mastery_weight", sa.Float(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("mastery_weight >= 0 AND mastery_weight <= 1", name="ck_subtopic_weight"),
        sa.ForeignKeyConstraint(["prerequisite_subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subtopic_id", "prerequisite_subtopic_id", name="uq_subtopic_prerequisite_pair"),
    )

    op.create_table(
        "problem_type_prerequisites",
        sa.Column("problem_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prerequisite_problem_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "problem_type_id <> prerequisite_problem_type_id",
            name="ck_problem_type_prerequisite_not_self",
        ),
        sa.ForeignKeyConstraint(["prerequisite_problem_type_id"], ["problem_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_type_id"], ["problem_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(
            "problem_type_id",
            "prerequisite_problem_type_id",
            name="pk_problem_type_prerequisites",
        ),
    )

    op.create_table(
        "problems",
        sa.Column("subtopic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("difficulty_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("solution", sa.Text(), nullable=False),
        sa.Column("condition_images", postgresql.JSONB(), nullable=False),
        sa.Column("solution_images", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["difficulty_id"], ["difficulties.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_type_id"], ["problem_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "problem_answer_options",
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("type", problem_answer_option_type_enum, nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "responses",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_option_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entrance_test_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["answer_option_id"], ["problem_answer_options.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entrance_test_session_id"], ["entrance_test_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    user_role_enum = postgresql.ENUM(
        "admin",
        "student",
        name="user_role_enum",
        create_type=False,
    )
    entrance_test_status_enum = postgresql.ENUM(
        "pending",
        "active",
        "completed",
        "skipped",
        name="entrance_test_status_enum",
        create_type=False,
    )
    problem_answer_option_type_enum = postgresql.ENUM(
        "right",
        "wrong",
        "i_dont_know",
        name="problem_answer_option_type_enum",
        create_type=False,
    )

    op.drop_table("responses")
    op.drop_table("problem_answer_options")
    op.drop_table("problems")
    op.drop_table("problem_type_prerequisites")
    op.drop_table("subtopic_prerequisites")
    op.drop_table("topic_subtopics")
    op.drop_table("entrance_test_sessions")
    op.drop_table("subtopics")
    op.drop_table("problem_types")
    op.drop_table("difficulties")
    op.drop_table("topics")
    op.drop_table("users")

    problem_answer_option_type_enum.drop(bind, checkfirst=True)
    entrance_test_status_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
