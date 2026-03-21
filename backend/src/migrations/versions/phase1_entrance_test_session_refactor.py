"""phase1 entrance test session refactor

Revision ID: phase1_entrance_refactor
Revises: phase0_initial_schema
Create Date: 2026-03-22 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase1_entrance_refactor"
down_revision: str | None = "phase0_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    problem_answer_option_type_enum = postgresql.ENUM(
        "right",
        "wrong",
        "i_dont_know",
        name="problem_answer_option_type_enum",
        create_type=False,
    )
    problem_answer_option_type_enum.create(bind, checkfirst=True)

    if _has_column("problem_answer_options", "is_correct"):
        if not _has_column("problem_answer_options", "type"):
            op.add_column(
                "problem_answer_options",
                sa.Column("type", problem_answer_option_type_enum, nullable=True),
            )
        op.execute(
            sa.text(
                """
                UPDATE problem_answer_options
                SET type = CASE
                    WHEN is_correct THEN 'right'
                    ELSE 'wrong'
                END
                WHERE type IS NULL
                """
            )
        )
        op.alter_column("problem_answer_options", "type", nullable=False)
        op.drop_column("problem_answer_options", "is_correct")

    if not _has_column("responses", "entrance_test_session_id"):
        op.add_column(
            "responses",
            sa.Column("entrance_test_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_responses_entrance_test_session_id",
            "responses",
            "entrance_test_sessions",
            ["entrance_test_session_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if _has_column("responses", "is_correct"):
        op.drop_column("responses", "is_correct")

    if not _has_column("entrance_test_sessions", "structure_version"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column("structure_version", sa.Integer(), nullable=False, server_default="1"),
        )
        op.alter_column(
            "entrance_test_sessions",
            "structure_version",
            server_default=None,
        )

    if not _has_column("entrance_test_sessions", "current_problem_id"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column("current_problem_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_entrance_test_sessions_current_problem_id",
            "entrance_test_sessions",
            "problems",
            ["current_problem_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if _has_column("entrance_test_sessions", "problem_ids") or _has_column(
        "entrance_test_sessions",
        "response_ids",
    ):
        _backfill_current_problem_id()

    _insert_missing_i_dont_know_options()

    if _has_column("entrance_test_sessions", "response_ids"):
        op.drop_column("entrance_test_sessions", "response_ids")

    if _has_column("entrance_test_sessions", "problem_ids"):
        op.drop_column("entrance_test_sessions", "problem_ids")


def downgrade() -> None:
    bind = op.get_bind()
    problem_answer_option_type_enum = postgresql.ENUM(
        "right",
        "wrong",
        "i_dont_know",
        name="problem_answer_option_type_enum",
        create_type=False,
    )

    if not _has_column("problem_answer_options", "is_correct"):
        op.add_column(
            "problem_answer_options",
            sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute(
            sa.text(
                """
                UPDATE problem_answer_options
                SET is_correct = CASE
                    WHEN type = 'right' THEN TRUE
                    ELSE FALSE
                END
                """
            )
        )
        op.alter_column("problem_answer_options", "is_correct", server_default=None)

    if _has_column("problem_answer_options", "type"):
        op.drop_column("problem_answer_options", "type")
        problem_answer_option_type_enum.drop(bind, checkfirst=True)

    if not _has_column("responses", "is_correct"):
        op.add_column(
            "responses",
            sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute(
            sa.text(
                """
                UPDATE responses
                SET is_correct = COALESCE((
                    SELECT problem_answer_options.is_correct
                    FROM problem_answer_options
                    WHERE problem_answer_options.id = responses.answer_option_id
                ), FALSE)
                """
            )
        )
        op.alter_column("responses", "is_correct", server_default=None)

    if _has_column("responses", "entrance_test_session_id"):
        op.drop_constraint(
            "fk_responses_entrance_test_session_id",
            "responses",
            type_="foreignkey",
        )
        op.drop_column("responses", "entrance_test_session_id")

    if not _has_column("entrance_test_sessions", "problem_ids"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column(
                "problem_ids",
                postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                nullable=False,
                server_default="{}",
            ),
        )
        op.alter_column("entrance_test_sessions", "problem_ids", server_default=None)

    if not _has_column("entrance_test_sessions", "response_ids"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column(
                "response_ids",
                postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                nullable=False,
                server_default="{}",
            ),
        )
        op.alter_column("entrance_test_sessions", "response_ids", server_default=None)

    if _has_column("entrance_test_sessions", "current_problem_id"):
        _restore_array_session_state()
        op.drop_constraint(
            "fk_entrance_test_sessions_current_problem_id",
            "entrance_test_sessions",
            type_="foreignkey",
        )
        op.drop_column("entrance_test_sessions", "current_problem_id")

    if _has_column("entrance_test_sessions", "structure_version"):
        op.drop_column("entrance_test_sessions", "structure_version")


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _backfill_current_problem_id() -> None:
    bind = op.get_bind()
    session_rows = bind.execute(
        sa.text(
            """
            SELECT id, status, problem_ids, response_ids
            FROM entrance_test_sessions
            """
        )
    ).mappings()

    for session_row in session_rows:
        problem_ids = list(session_row["problem_ids"] or [])
        response_ids = list(session_row["response_ids"] or [])
        current_problem_id: uuid.UUID | None = None

        if session_row["status"] in {"pending", "active"}:
            response_count = len(response_ids)
            if response_count < len(problem_ids):
                current_problem_id = problem_ids[response_count]

        bind.execute(
            sa.text(
                """
                UPDATE entrance_test_sessions
                SET structure_version = COALESCE(structure_version, 1),
                    current_problem_id = :current_problem_id
                WHERE id = :session_id
                """
            ),
            {
                "session_id": session_row["id"],
                "current_problem_id": current_problem_id,
            },
        )


def _insert_missing_i_dont_know_options() -> None:
    bind = op.get_bind()
    problem_ids = bind.execute(
        sa.text(
            """
            SELECT problems.id
            FROM problems
            WHERE NOT EXISTS (
                SELECT 1
                FROM problem_answer_options
                WHERE problem_answer_options.problem_id = problems.id
                  AND problem_answer_options.type = 'i_dont_know'
            )
            """
        )
    ).scalars()

    for problem_id in problem_ids:
        bind.execute(
            sa.text(
                """
                INSERT INTO problem_answer_options (id, problem_id, text, type)
                VALUES (:id, :problem_id, :text, :type)
                """
            ),
            {
                "id": uuid.uuid4(),
                "problem_id": problem_id,
                "text": "I don't know",
                "type": "i_dont_know",
            },
        )


def _restore_array_session_state() -> None:
    bind = op.get_bind()
    session_rows = bind.execute(
        sa.text(
            """
            SELECT id, status, current_problem_id
            FROM entrance_test_sessions
            """
        )
    ).mappings()

    for session_row in session_rows:
        problem_ids: list[uuid.UUID] = []
        if session_row["current_problem_id"] is not None and session_row["status"] in {"pending", "active"}:
            problem_ids = [session_row["current_problem_id"]]

        bind.execute(
            sa.text(
                """
                UPDATE entrance_test_sessions
                SET problem_ids = :problem_ids,
                    response_ids = '{}'
                WHERE id = :session_id
                """
            ),
            {
                "session_id": session_row["id"],
                "problem_ids": problem_ids,
            },
        )
