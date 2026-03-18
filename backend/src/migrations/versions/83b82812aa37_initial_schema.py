from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from src.core.utils import PasswordTools
from src.db.catalog_data import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DIFFICULTIES,
    SAMPLE_PROBLEMS,
    SKILL_SUBSKILLS,
    TOPIC_SUBTOPICS,
    build_stable_uuid,
)
from src.db.enums import UserRole

revision = "83b82812aa37"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "difficulties",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("coefficient", sa.Float(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "skills",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "topics",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("admin", "student", name="user_role_enum"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "subskills",
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "name", name="uq_subskill_skill_name"),
    )
    op.create_table(
        "subtopics",
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "name", name="uq_subtopic_topic_name"),
    )
    op.create_table(
        "problems",
        sa.Column("subtopic_id", sa.UUID(), nullable=False),
        sa.Column("difficulty_id", sa.UUID(), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("solution", sa.Text(), nullable=False),
        sa.Column("right_answer", sa.Text(), nullable=False),
        sa.Column("condition_images", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("solution_images", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["difficulty_id"], ["difficulties.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subskill_prerequisites",
        sa.Column("subskill_id", sa.UUID(), nullable=False),
        sa.Column("prerequisite_subskill_id", sa.UUID(), nullable=False),
        sa.Column("mastery_weight", sa.Float(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("mastery_weight >= 0 AND mastery_weight <= 1", name="ck_subskill_weight"),
        sa.ForeignKeyConstraint(["prerequisite_subskill_id"], ["subskills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subskill_id"], ["subskills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subskill_id", "prerequisite_subskill_id", name="uq_subskill_prerequisite_pair"),
    )
    op.create_table(
        "subtopic_prerequisites",
        sa.Column("subtopic_id", sa.UUID(), nullable=False),
        sa.Column("prerequisite_subtopic_id", sa.UUID(), nullable=False),
        sa.Column("mastery_weight", sa.Float(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("mastery_weight >= 0 AND mastery_weight <= 1", name="ck_subtopic_weight"),
        sa.ForeignKeyConstraint(["prerequisite_subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subtopic_id", "prerequisite_subtopic_id", name="uq_subtopic_prerequisite_pair"),
    )
    op.create_table(
        "problem_answer_options",
        sa.Column("problem_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "problem_subskills",
        sa.Column("problem_id", sa.UUID(), nullable=False),
        sa.Column("subskill_id", sa.UUID(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_problem_subskill_weight"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subskill_id"], ["subskills.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("problem_id", "subskill_id", name="pk_problem_subskills"),
    )
    op.create_table(
        "user_failed_problems",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("problem_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "problem_id", name="pk_user_failed_problem"),
    )
    op.create_table(
        "user_solved_problems",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("problem_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "problem_id", name="pk_user_solved_problem"),
    )
    seed_catalog_data()


def seed_catalog_data() -> None:
    difficulty_table = sa.table(
        "difficulties",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("coefficient", sa.Float()),
    )
    topic_table = sa.table(
        "topics",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
    )
    subtopic_table = sa.table(
        "subtopics",
        sa.column("id", sa.UUID()),
        sa.column("topic_id", sa.UUID()),
        sa.column("name", sa.String()),
    )
    skill_table = sa.table(
        "skills",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
    )
    subskill_table = sa.table(
        "subskills",
        sa.column("id", sa.UUID()),
        sa.column("skill_id", sa.UUID()),
        sa.column("name", sa.String()),
    )
    user_table = sa.table(
        "users",
        sa.column("id", sa.UUID()),
        sa.column("email", sa.String()),
        sa.column("first_name", sa.String()),
        sa.column("last_name", sa.String()),
        sa.column("avatar_url", sa.String()),
        sa.column("hashed_password", sa.String()),
        sa.column("role", sa.Enum("admin", "student", name="user_role_enum")),
        sa.column("is_active", sa.Boolean()),
    )
    problem_table = sa.table(
        "problems",
        sa.column("id", sa.UUID()),
        sa.column("subtopic_id", sa.UUID()),
        sa.column("difficulty_id", sa.UUID()),
        sa.column("condition", sa.Text()),
        sa.column("solution", sa.Text()),
        sa.column("right_answer", sa.Text()),
        sa.column("condition_images", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("solution_images", postgresql.JSONB(astext_type=sa.Text())),
    )
    answer_option_table = sa.table(
        "problem_answer_options",
        sa.column("id", sa.UUID()),
        sa.column("problem_id", sa.UUID()),
        sa.column("text", sa.Text()),
    )
    problem_subskill_table = sa.table(
        "problem_subskills",
        sa.column("problem_id", sa.UUID()),
        sa.column("subskill_id", sa.UUID()),
        sa.column("weight", sa.Float()),
    )

    difficulty_rows = [
        {
            "id": build_stable_uuid("difficulty", name),
            "name": name,
            "coefficient": coefficient,
        }
        for name, coefficient in DIFFICULTIES
    ]
    op.bulk_insert(difficulty_table, difficulty_rows)
    difficulty_ids = {row["name"]: row["id"] for row in difficulty_rows}

    topic_rows: list[dict[str, object]] = []
    subtopic_rows: list[dict[str, object]] = []
    subtopic_ids: dict[str, object] = {}
    for topic_name, subtopic_names in TOPIC_SUBTOPICS.items():
        topic_id = build_stable_uuid("topic", topic_name)
        topic_rows.append({"id": topic_id, "name": topic_name})
        for subtopic_name in subtopic_names:
            subtopic_id = build_stable_uuid("subtopic", f"{topic_name}:{subtopic_name}")
            subtopic_rows.append(
                {
                    "id": subtopic_id,
                    "topic_id": topic_id,
                    "name": subtopic_name,
                }
            )
            subtopic_ids[subtopic_name] = subtopic_id

    op.bulk_insert(topic_table, topic_rows)
    op.bulk_insert(subtopic_table, subtopic_rows)

    skill_rows: list[dict[str, object]] = []
    subskill_rows: list[dict[str, object]] = []
    subskill_ids: dict[str, object] = {}
    for skill_name, subskill_names in SKILL_SUBSKILLS.items():
        skill_id = build_stable_uuid("skill", skill_name)
        skill_rows.append({"id": skill_id, "name": skill_name})
        for subskill_name in subskill_names:
            subskill_id = build_stable_uuid("subskill", f"{skill_name}:{subskill_name}")
            subskill_rows.append(
                {
                    "id": subskill_id,
                    "skill_id": skill_id,
                    "name": subskill_name,
                }
            )
            subskill_ids[subskill_name] = subskill_id

    op.bulk_insert(skill_table, skill_rows)
    op.bulk_insert(subskill_table, subskill_rows)

    op.bulk_insert(
        user_table,
        [
            {
                "id": build_stable_uuid("user", ADMIN_EMAIL),
                "email": ADMIN_EMAIL,
                "first_name": "Admin",
                "last_name": "User",
                "avatar_url": None,
                "hashed_password": PasswordTools.hash_password(ADMIN_PASSWORD),
                "role": UserRole.ADMIN.value,
                "is_active": True,
            }
        ],
    )

    problem_rows: list[dict[str, object]] = []
    answer_option_rows: list[dict[str, object]] = []
    problem_subskill_rows: list[dict[str, object]] = []
    for problem in SAMPLE_PROBLEMS:
        problem_id = build_stable_uuid("problem", problem["key"])
        problem_rows.append(
            {
                "id": problem_id,
                "subtopic_id": subtopic_ids[problem["subtopic"]],
                "difficulty_id": difficulty_ids[problem["difficulty"]],
                "condition": problem["condition"],
                "solution": problem["solution"],
                "right_answer": problem["right_answer"],
                "condition_images": problem["condition_images"],
                "solution_images": problem["solution_images"],
            }
        )

        for option in problem["answer_options"]:
            answer_option_rows.append(
                {
                    "id": build_stable_uuid("answer_option", f"{problem['key']}:{option}"),
                    "problem_id": problem_id,
                    "text": option,
                }
            )

        for subskill in problem["subskills"]:
            problem_subskill_rows.append(
                {
                    "problem_id": problem_id,
                    "subskill_id": subskill_ids[subskill["name"]],
                    "weight": subskill["weight"],
                }
            )

    op.bulk_insert(problem_table, problem_rows)
    op.bulk_insert(answer_option_table, answer_option_rows)
    op.bulk_insert(problem_subskill_table, problem_subskill_rows)


def downgrade() -> None:
    op.drop_table("user_solved_problems")
    op.drop_table("user_failed_problems")
    op.drop_table("problem_subskills")
    op.drop_table("problem_answer_options")
    op.drop_table("subtopic_prerequisites")
    op.drop_table("subskill_prerequisites")
    op.drop_table("problems")
    op.drop_table("subtopics")
    op.drop_table("subskills")
    op.drop_table("users")
    op.drop_table("topics")
    op.drop_table("skills")
    op.drop_table("difficulties")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
