"""phase7 course dag assessment foundation

Revision ID: phase7_course_dag_assessment
Revises: phase6_projection_confidence
Create Date: 2026-03-27 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import uuid
from typing import TypedDict

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase7_course_dag_assessment"
down_revision: str | None = "phase6_projection_confidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_COURSE_TITLE = "Profile Mathematics (Grades 10-11)"


class MigrationGraphContext(TypedDict):
    course_id: uuid.UUID
    graph_version_id: uuid.UUID
    course_node_by_problem_type_id: dict[uuid.UUID, uuid.UUID]
    all_course_node_ids: list[uuid.UUID]


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

    _migrate_legacy_data(bind)


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


def _migrate_legacy_data(bind: sa.Connection) -> None:
    if not _table_exists(bind, "entrance_test_sessions"):
        return

    if not _table_exists(bind, "entrance_test_structures"):
        return

    author_user_id = _load_author_user_id(bind)
    if author_user_id is None:
        return

    graph_context = _ensure_demo_course_graph(bind, author_user_id)
    _migrate_legacy_sessions(bind, graph_context)
    _link_response_course_nodes(bind)


def _table_exists(bind: sa.Connection, table_name: str) -> bool:
    query = sa.text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :table_name
        )
        """
    )
    return bool(bind.execute(query, {"table_name": table_name}).scalar_one())


def _load_author_user_id(bind: sa.Connection) -> uuid.UUID | None:
    admin_user_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM users
            WHERE role = 'admin'
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if isinstance(admin_user_id, uuid.UUID):
        return admin_user_id

    student_user_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM users
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if isinstance(student_user_id, uuid.UUID):
        return student_user_id

    return None


def _ensure_demo_course_graph(
    bind: sa.Connection,
    author_user_id: uuid.UUID,
) -> MigrationGraphContext:
    now = datetime.now(UTC)
    course_row = bind.execute(
        sa.text(
            """
            SELECT id, current_graph_version_id
            FROM courses
            WHERE title = :title
            ORDER BY created_at ASC
            LIMIT 1
            """
        ),
        {"title": DEMO_COURSE_TITLE},
    ).mappings().one_or_none()

    if course_row is None:
        course_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO courses (
                    id, author_id, title, description, current_graph_version_id, created_at, updated_at
                )
                VALUES (
                    :id, :author_id, :title, :description, NULL, :now, :now
                )
                """
            ),
            {
                "id": course_id,
                "author_id": author_user_id,
                "title": DEMO_COURSE_TITLE,
                "description": "Single published diploma demo course for profile mathematics grades 10-11.",
                "now": now,
            },
        )
    else:
        course_id = course_row["id"]

    problem_types = bind.execute(
        sa.text(
            """
            SELECT id, name
            FROM problem_types
            ORDER BY name ASC
            """
        )
    ).mappings().all()

    node_rows = bind.execute(
        sa.text(
            """
            SELECT id, problem_type_id, name
            FROM course_nodes
            WHERE course_id = :course_id
            """
        ),
        {"course_id": course_id},
    ).mappings().all()

    node_by_problem_type_id: dict[uuid.UUID, dict[str, object]] = {}
    for row in node_rows:
        problem_type_id = row["problem_type_id"]
        if not isinstance(problem_type_id, uuid.UUID):
            continue

        node_by_problem_type_id[problem_type_id] = {
            "id": row["id"],
            "problem_type_id": problem_type_id,
            "name": row["name"],
        }

    for problem_type in problem_types:
        problem_type_id = problem_type["id"]
        if problem_type_id in node_by_problem_type_id:
            continue

        course_node_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO course_nodes (
                    id, course_id, problem_type_id, name, description, created_at, updated_at
                )
                VALUES (
                    :id, :course_id, :problem_type_id, :name, :description, :now, :now
                )
                """
            ),
            {
                "id": course_node_id,
                "course_id": course_id,
                "problem_type_id": problem_type_id,
                "name": problem_type["name"],
                "description": problem_type["name"],
                "now": now,
            },
        )
        node_by_problem_type_id[problem_type_id] = {
            "id": course_node_id,
            "problem_type_id": problem_type_id,
            "name": problem_type["name"],
        }

    for problem_type_id, course_node in node_by_problem_type_id.items():
        bind.execute(
            sa.text(
                """
                UPDATE problems
                SET course_node_id = :course_node_id
                WHERE problem_type_id = :problem_type_id
                """
            ),
            {
                "course_node_id": course_node["id"],
                "problem_type_id": problem_type_id,
            },
        )

    graph_version_row = bind.execute(
        sa.text(
            """
            SELECT id
            FROM course_graph_versions
            WHERE course_id = :course_id
            ORDER BY version_number DESC, created_at DESC
            LIMIT 1
            """
        ),
        {"course_id": course_id},
    ).mappings().one_or_none()

    if graph_version_row is None:
        graph_version_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO course_graph_versions (
                    id, course_id, version_number, status, node_count, edge_count, built_at, error_message, created_at, updated_at
                )
                VALUES (
                    :id, :course_id, 1, 'ready', 0, 0, :now, NULL, :now, :now
                )
                """
            ),
            {
                "id": graph_version_id,
                "course_id": course_id,
                "now": now,
            },
        )
    else:
        graph_version_id = graph_version_row["id"]

    sorted_nodes = sorted(
        node_by_problem_type_id.values(),
        key=lambda item: str(item["name"]),
    )

    for rank, course_node in enumerate(sorted_nodes, start=1):
        exists = bind.execute(
            sa.text(
                """
                SELECT id
                FROM course_graph_version_nodes
                WHERE graph_version_id = :graph_version_id AND course_node_id = :course_node_id
                LIMIT 1
                """
            ),
            {
                "graph_version_id": graph_version_id,
                "course_node_id": course_node["id"],
            },
        ).scalar_one_or_none()
        if exists is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO course_graph_version_nodes (
                        id, graph_version_id, course_node_id, lecture_id, topological_rank, created_at, updated_at
                    )
                    VALUES (
                        :id, :graph_version_id, :course_node_id, NULL, :topological_rank, :now, :now
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "graph_version_id": graph_version_id,
                    "course_node_id": course_node["id"],
                    "topological_rank": rank,
                    "now": now,
                },
            )

    prerequisite_rows = bind.execute(
        sa.text(
            """
            SELECT problem_type_id, prerequisite_problem_type_id
            FROM problem_type_prerequisites
            """
        )
    ).mappings().all()

    for prerequisite_row in prerequisite_rows:
        dependent_node = node_by_problem_type_id.get(prerequisite_row["problem_type_id"])
        prerequisite_node = node_by_problem_type_id.get(prerequisite_row["prerequisite_problem_type_id"])
        if dependent_node is None or prerequisite_node is None:
            continue

        edge_exists = bind.execute(
            sa.text(
                """
                SELECT id
                FROM course_graph_version_edges
                WHERE graph_version_id = :graph_version_id
                  AND prerequisite_course_node_id = :prerequisite_course_node_id
                  AND dependent_course_node_id = :dependent_course_node_id
                LIMIT 1
                """
            ),
            {
                "graph_version_id": graph_version_id,
                "prerequisite_course_node_id": prerequisite_node["id"],
                "dependent_course_node_id": dependent_node["id"],
            },
        ).scalar_one_or_none()
        if edge_exists is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO course_graph_version_edges (
                        id, graph_version_id, prerequisite_course_node_id, dependent_course_node_id, created_at, updated_at
                    )
                    VALUES (
                        :id, :graph_version_id, :prerequisite_course_node_id, :dependent_course_node_id, :now, :now
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "graph_version_id": graph_version_id,
                    "prerequisite_course_node_id": prerequisite_node["id"],
                    "dependent_course_node_id": dependent_node["id"],
                    "now": now,
                },
            )

    node_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM course_graph_version_nodes
            WHERE graph_version_id = :graph_version_id
            """
        ),
        {"graph_version_id": graph_version_id},
    ).scalar_one()
    edge_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM course_graph_version_edges
            WHERE graph_version_id = :graph_version_id
            """
        ),
        {"graph_version_id": graph_version_id},
    ).scalar_one()

    bind.execute(
        sa.text(
            """
            UPDATE course_graph_versions
            SET status = 'ready',
                node_count = :node_count,
                edge_count = :edge_count,
                built_at = :built_at,
                error_message = NULL,
                updated_at = :updated_at
            WHERE id = :graph_version_id
            """
        ),
        {
            "graph_version_id": graph_version_id,
            "node_count": node_count,
            "edge_count": edge_count,
            "built_at": now,
            "updated_at": now,
        },
    )

    bind.execute(
        sa.text(
            """
            UPDATE courses
            SET current_graph_version_id = :graph_version_id, updated_at = :updated_at
            WHERE id = :course_id
            """
        ),
        {
            "course_id": course_id,
            "graph_version_id": graph_version_id,
            "updated_at": now,
        },
    )

    all_course_node_ids: list[uuid.UUID] = []
    for item in sorted_nodes:
        raw_course_node_id = item["id"]
        if not isinstance(raw_course_node_id, uuid.UUID):
            continue
        all_course_node_ids.append(raw_course_node_id)

    return {
        "course_id": course_id,
        "graph_version_id": graph_version_id,
        "course_node_by_problem_type_id": {
            problem_type_id: item["id"]
            for problem_type_id, item in node_by_problem_type_id.items()
            if isinstance(item["id"], uuid.UUID)
        },
        "all_course_node_ids": all_course_node_ids,
    }


def _migrate_legacy_sessions(
    bind: sa.Connection,
    graph_context: MigrationGraphContext,
) -> None:
    graph_version_id = graph_context["graph_version_id"]
    course_node_by_problem_type_id = graph_context["course_node_by_problem_type_id"]
    all_course_node_ids = graph_context["all_course_node_ids"]
    course_id = graph_context["course_id"]
    now = datetime.now(UTC)

    sessions = bind.execute(
        sa.text(
            """
            SELECT id, user_id, status, started_at, completed_at, skipped_at,
                   structure_version, current_problem_id,
                   final_state_index, final_state_probability,
                   learned_problem_type_ids, inner_fringe_problem_type_ids, outer_fringe_problem_type_ids,
                   business_config_snapshot
            FROM entrance_test_sessions
            ORDER BY created_at ASC, id ASC
            """
        )
    ).mappings().all()

    if not sessions:
        return

    latest_completed_session_by_user_id: dict[uuid.UUID, uuid.UUID] = {}
    latest_completed_at_by_user_id: dict[uuid.UUID, datetime] = {}
    for session in sessions:
        if session["status"] != "completed":
            continue
        measured_at = session["completed_at"] or now
        user_id = session["user_id"]
        previous = latest_completed_at_by_user_id.get(user_id)
        if previous is None or measured_at >= previous:
            latest_completed_at_by_user_id[user_id] = measured_at
            latest_completed_session_by_user_id[user_id] = session["id"]

    attempt_id_by_session_id: dict[uuid.UUID, uuid.UUID] = {}
    for session in sessions:
        user_id = session["user_id"]
        attempt_id = uuid.uuid4()
        attempt_id_by_session_id[session["id"]] = attempt_id

        bind.execute(
            sa.text(
                """
                INSERT INTO course_enrollments (id, user_id, course_id, is_active, created_at, updated_at)
                VALUES (:id, :user_id, :course_id, true, :now, :now)
                ON CONFLICT (user_id, course_id)
                DO UPDATE SET is_active = true, updated_at = :now
                """
            ),
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "course_id": course_id,
                "now": now,
            },
        )

        current_course_node_id = bind.execute(
            sa.text(
                """
                SELECT course_node_id
                FROM problems
                WHERE id = :problem_id
                LIMIT 1
                """
            ),
            {"problem_id": session["current_problem_id"]},
        ).scalar_one_or_none()
        runtime_status = _map_legacy_session_status_to_attempt_status(session["status"])
        ended_at = session["completed_at"] or session["skipped_at"]
        metadata_json = {
            "runtime_kind": "legacy_migrated",
            "asked_course_node_ids": [],
            "learned_course_node_ids": [],
            "failed_course_node_ids": [],
            "target_course_node_ids": [],
            "current_course_node_id": str(current_course_node_id) if current_course_node_id is not None else None,
            "assessment_node_score_by_course_node_id": {},
            "legacy_session_id": str(session["id"]),
            "legacy_status": session["status"],
        }
        config_snapshot = {
            "source": "legacy_entrance_test_session",
            "legacy_structure_version": session["structure_version"],
            "legacy_business_config_snapshot": session["business_config_snapshot"] or {},
        }
        bind.execute(
            sa.text(
                """
                INSERT INTO test_attempts (
                    id, user_id, graph_version_id, kind, status, current_problem_id,
                    config_snapshot, metadata_json, started_at, paused_at, ended_at, created_at, updated_at
                )
                VALUES (
                    :id, :user_id, :graph_version_id, 'entrance', :status, :current_problem_id,
                    :config_snapshot, :metadata_json, :started_at, NULL, :ended_at, :now, :now
                )
                """
            ),
            {
                "id": attempt_id,
                "user_id": user_id,
                "graph_version_id": graph_version_id,
                "status": runtime_status,
                "current_problem_id": session["current_problem_id"],
                "config_snapshot": config_snapshot,
                "metadata_json": metadata_json,
                "started_at": session["started_at"],
                "ended_at": ended_at,
                "now": now,
            },
        )

    for session_id, attempt_id in attempt_id_by_session_id.items():
        bind.execute(
            sa.text(
                """
                UPDATE responses
                SET test_attempt_id = :test_attempt_id
                WHERE entrance_test_session_id = :session_id
                """
            ),
            {
                "session_id": session_id,
                "test_attempt_id": attempt_id,
            },
        )

    for session in sessions:
        if session["status"] != "completed":
            continue
        if session["final_state_index"] is None or session["final_state_probability"] is None:
            continue

        session_id = session["id"]
        attempt_id = attempt_id_by_session_id[session_id]
        user_id = session["user_id"]
        learned_ids = _map_problem_type_ids_to_course_node_ids(
            course_node_by_problem_type_id,
            session["learned_problem_type_ids"] or [],
        )
        ready_ids = _map_problem_type_ids_to_course_node_ids(
            course_node_by_problem_type_id,
            session["inner_fringe_problem_type_ids"] or [],
        )
        frontier_ids = _map_problem_type_ids_to_course_node_ids(
            course_node_by_problem_type_id,
            session["outer_fringe_problem_type_ids"] or [],
        )
        answered_ids = _load_answered_course_node_ids(bind, session_id)
        locked_ids = [
            course_node_id
            for course_node_id in all_course_node_ids
            if course_node_id not in learned_ids and course_node_id not in ready_ids
        ]
        measured_at = session["completed_at"] or now
        is_active = latest_completed_session_by_user_id.get(user_id) == session_id
        state = {
            "learned_course_node_ids": [str(item) for item in learned_ids],
            "ready_course_node_ids": [str(item) for item in ready_ids],
            "locked_course_node_ids": [str(item) for item in locked_ids],
            "failed_course_node_ids": [],
            "answered_course_node_ids": [str(item) for item in answered_ids],
        }
        metadata_json = {
            "legacy_session_id": str(session_id),
            "legacy_final_state_index": session["final_state_index"],
            "legacy_frontier_course_node_ids": [str(item) for item in frontier_ids],
            "migration_source": "phase6_projection_confidence",
        }

        bind.execute(
            sa.text(
                """
                INSERT INTO graph_assessments (
                    id, user_id, graph_version_id, source_test_attempt_id, state, state_confidence,
                    is_active, assessment_kind, metadata_json, measured_at, created_at, updated_at
                )
                VALUES (
                    :id, :user_id, :graph_version_id, :source_test_attempt_id, :state, :state_confidence,
                    :is_active, 'entrance', :metadata_json, :measured_at, :now, :now
                )
                ON CONFLICT (source_test_attempt_id) DO NOTHING
                """
            ),
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "graph_version_id": graph_version_id,
                "source_test_attempt_id": attempt_id,
                "state": state,
                "state_confidence": float(session["final_state_probability"]),
                "is_active": is_active,
                "metadata_json": metadata_json,
                "measured_at": measured_at,
                "now": now,
            },
        )


def _link_response_course_nodes(bind: sa.Connection) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE responses AS response_event
            SET course_node_id = problem.course_node_id
            FROM problems AS problem
            WHERE response_event.problem_id = problem.id
              AND response_event.course_node_id IS NULL
              AND problem.course_node_id IS NOT NULL
            """
        )
    )


def _map_legacy_session_status_to_attempt_status(legacy_status: str) -> str:
    if legacy_status == "completed":
        return "completed"
    if legacy_status == "active":
        return "active"
    if legacy_status == "pending":
        return "paused"
    return "cancelled"


def _map_problem_type_ids_to_course_node_ids(
    course_node_by_problem_type_id: dict[uuid.UUID, uuid.UUID],
    problem_type_ids: list[object],
) -> list[uuid.UUID]:
    mapped_course_node_ids: list[uuid.UUID] = []
    for raw_problem_type_id in problem_type_ids:
        if isinstance(raw_problem_type_id, uuid.UUID):
            problem_type_id = raw_problem_type_id
        else:
            try:
                problem_type_id = uuid.UUID(str(raw_problem_type_id))
            except ValueError:
                continue
        course_node_id = course_node_by_problem_type_id.get(problem_type_id)
        if course_node_id is not None and course_node_id not in mapped_course_node_ids:
            mapped_course_node_ids.append(course_node_id)
    return mapped_course_node_ids


def _load_answered_course_node_ids(bind: sa.Connection, session_id: uuid.UUID) -> list[uuid.UUID]:
    answered_rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT response_event.course_node_id
            FROM responses AS response_event
            WHERE response_event.entrance_test_session_id = :session_id
              AND response_event.course_node_id IS NOT NULL
            """
        ),
        {"session_id": session_id},
    ).scalars().all()
    return [item for item in answered_rows if isinstance(item, uuid.UUID)]
