"""phase7 course dag assessment foundation

Revision ID: phase7_course_dag_assessment
Revises: phase0_initial_schema
Create Date: 2026-03-27 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase7_course_dag_assessment"
down_revision: str | None = "phase0_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    course_graph_version_status_enum = postgresql.ENUM(
        "draft",
        "ready",
        "failed",
        "archived",
        name="course_graph_version_status_enum",
        create_type=False,
    )
    test_attempt_kind_enum = postgresql.ENUM(
        "entrance",
        "general",
        name="test_attempt_kind_enum",
        create_type=False,
    )
    test_attempt_status_enum = postgresql.ENUM(
        "active",
        "paused",
        "completed",
        "cancelled",
        name="test_attempt_status_enum",
        create_type=False,
    )

    course_graph_version_status_enum.create(bind, checkfirst=True)
    test_attempt_kind_enum.create(bind, checkfirst=True)
    test_attempt_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "courses",
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_graph_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "course_enrollments",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "course_id", name="uq_course_enrollments_user_course"),
    )

    op.create_table(
        "course_nodes",
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["problem_type_id"],
            ["problem_types.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "name", name="uq_course_nodes_course_name"),
    )

    op.create_table(
        "lectures",
        sa.Column("course_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
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
        sa.ForeignKeyConstraint(["course_node_id"], ["course_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "course_graph_versions",
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", course_graph_version_status_enum, nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "course_id",
            "version_number",
            name="uq_course_graph_versions_course_version",
        ),
    )

    op.create_foreign_key(
        "fk_courses_current_graph_version_id",
        "courses",
        "course_graph_versions",
        ["current_graph_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "course_graph_version_nodes",
        sa.Column("graph_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lecture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("topological_rank", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["course_node_id"],
            ["course_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["graph_version_id"],
            ["course_graph_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "graph_version_id",
            "course_node_id",
            name="uq_course_graph_version_nodes_membership",
        ),
    )

    op.create_table(
        "course_graph_version_edges",
        sa.Column("graph_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prerequisite_course_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependent_course_node_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.CheckConstraint(
            "prerequisite_course_node_id <> dependent_course_node_id",
            name="ck_course_graph_version_edge_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["dependent_course_node_id"],
            ["course_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["graph_version_id"],
            ["course_graph_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_course_node_id"],
            ["course_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "graph_version_id",
            "prerequisite_course_node_id",
            "dependent_course_node_id",
            name="uq_course_graph_version_edges_membership",
        ),
    )

    op.create_table(
        "lecture_pages",
        sa.Column("lecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_content", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lecture_id",
            "page_number",
            name="uq_lecture_pages_lecture_page_number",
        ),
    )

    op.create_table(
        "test_attempts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", test_attempt_kind_enum, nullable=False),
        sa.Column("status", test_attempt_status_enum, nullable=False),
        sa.Column("current_problem_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["current_problem_id"],
            ["problems.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["graph_version_id"],
            ["course_graph_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_test_attempts_active_user",
        "test_attempts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "graph_assessments",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_test_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state_confidence", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("assessment_kind", test_attempt_kind_enum, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["graph_version_id"],
            ["course_graph_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_test_attempt_id"],
            ["test_attempts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_test_attempt_id"),
    )

    op.add_column(
        "problems",
        sa.Column("course_node_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_problems_course_node_id",
        "problems",
        "course_nodes",
        ["course_node_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "responses",
        sa.Column("test_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "responses",
        sa.Column("course_node_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_responses_test_attempt_id",
        "responses",
        "test_attempts",
        ["test_attempt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_responses_course_node_id",
        "responses",
        "course_nodes",
        ["course_node_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    course_graph_version_status_enum = postgresql.ENUM(
        "draft",
        "ready",
        "failed",
        "archived",
        name="course_graph_version_status_enum",
        create_type=False,
    )
    test_attempt_kind_enum = postgresql.ENUM(
        "entrance",
        "general",
        name="test_attempt_kind_enum",
        create_type=False,
    )
    test_attempt_status_enum = postgresql.ENUM(
        "active",
        "paused",
        "completed",
        "cancelled",
        name="test_attempt_status_enum",
        create_type=False,
    )

    op.drop_constraint("fk_responses_course_node_id", "responses", type_="foreignkey")
    op.drop_constraint("fk_responses_test_attempt_id", "responses", type_="foreignkey")
    op.drop_column("responses", "course_node_id")
    op.drop_column("responses", "test_attempt_id")

    op.drop_constraint("fk_problems_course_node_id", "problems", type_="foreignkey")
    op.drop_column("problems", "course_node_id")

    op.drop_table("graph_assessments")
    op.drop_index("uq_test_attempts_active_user", table_name="test_attempts")
    op.drop_table("test_attempts")
    op.drop_table("lecture_pages")
    op.drop_table("course_graph_version_edges")
    op.drop_table("course_graph_version_nodes")
    op.drop_constraint("fk_courses_current_graph_version_id", "courses", type_="foreignkey")
    op.drop_table("course_graph_versions")
    op.drop_table("lectures")
    op.drop_table("course_nodes")
    op.drop_table("course_enrollments")
    op.drop_table("courses")

    test_attempt_status_enum.drop(bind, checkfirst=True)
    test_attempt_kind_enum.drop(bind, checkfirst=True)
    course_graph_version_status_enum.drop(bind, checkfirst=True)
