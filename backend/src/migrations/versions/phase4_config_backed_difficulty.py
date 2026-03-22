"""phase4 config-backed difficulty and session snapshots

Revision ID: phase4_config_difficulty
Revises: phase3_entrance_test_structure
Create Date: 2026-03-23 01:40:00.000000
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import tomllib
from typing import cast
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase4_config_difficulty"
down_revision: str | None = "phase3_entrance_test_structure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DIFFICULTY_LEVELS = (
    "elementary",
    "intermediate",
    "upper_intermediate",
    "advanced",
    "proficient",
)
DIFFICULTY_NAME_MAPPING = {
    "very easy": "elementary",
    "easy": "intermediate",
    "medium": "upper_intermediate",
    "hard": "advanced",
    "very hard": "proficient",
}
LEGACY_DIFFICULTY_NAME_MAPPING = {
    "elementary": "very easy",
    "intermediate": "easy",
    "upper_intermediate": "medium",
    "advanced": "hard",
    "proficient": "very hard",
}


def upgrade() -> None:
    bind = op.get_bind()
    difficulty_level_enum = postgresql.ENUM(
        *DIFFICULTY_LEVELS,
        name="difficulty_level_enum",
        create_type=False,
    )
    difficulty_level_enum.create(bind, checkfirst=True)

    if _has_table("difficulties"):
        _assert_known_difficulty_names()

    if not _has_column("problems", "difficulty"):
        op.add_column(
            "problems",
            sa.Column("difficulty", difficulty_level_enum, nullable=True),
        )

    if _has_table("difficulties") and _has_column("problems", "difficulty_id"):
        _backfill_problem_difficulty()

    _assert_no_missing_problem_difficulty()
    op.alter_column("problems", "difficulty", nullable=False)

    _ensure_response_snapshot_columns(difficulty_level_enum)
    _backfill_response_snapshots()

    if not _has_column("entrance_test_sessions", "business_config_snapshot"):
        op.add_column(
            "entrance_test_sessions",
            sa.Column("business_config_snapshot", postgresql.JSONB(), nullable=True),
        )
    _backfill_business_config_snapshot()

    if _has_column("problems", "difficulty_id"):
        _drop_foreign_keys("problems", "difficulty_id")
        op.drop_column("problems", "difficulty_id")

    if _has_table("difficulties"):
        op.drop_table("difficulties")


def downgrade() -> None:
    bind = op.get_bind()
    difficulty_level_enum = postgresql.ENUM(
        *DIFFICULTY_LEVELS,
        name="difficulty_level_enum",
        create_type=False,
    )

    if not _has_table("difficulties"):
        op.create_table(
            "difficulties",
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("coefficient", sa.Float(), nullable=False),
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    _restore_legacy_difficulties()

    if not _has_column("problems", "difficulty_id"):
        op.add_column(
            "problems",
            sa.Column("difficulty_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if _has_column("problems", "difficulty"):
        _backfill_problem_difficulty_id()
        op.alter_column("problems", "difficulty_id", nullable=False)
        op.create_foreign_key(
            "fk_problems_difficulty_id_difficulties",
            "problems",
            "difficulties",
            ["difficulty_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.drop_column("problems", "difficulty")

    if _has_column("entrance_test_sessions", "business_config_snapshot"):
        op.drop_column("entrance_test_sessions", "business_config_snapshot")

    if _has_column("responses", "difficulty_weight"):
        op.drop_column("responses", "difficulty_weight")
    if _has_column("responses", "difficulty"):
        op.drop_column("responses", "difficulty")
    if _has_column("responses", "answer_option_type"):
        op.drop_column("responses", "answer_option_type")
    if _has_column("responses", "problem_type_id"):
        op.drop_column("responses", "problem_type_id")

    if not _has_column("problems", "difficulty") and not _has_column("responses", "difficulty"):
        difficulty_level_enum.drop(bind, checkfirst=True)


def _ensure_response_snapshot_columns(
    difficulty_level_enum: postgresql.ENUM,
) -> None:
    bind = op.get_bind()
    problem_answer_option_type_enum = postgresql.ENUM(
        "right",
        "wrong",
        "i_dont_know",
        name="problem_answer_option_type_enum",
        create_type=False,
    )
    problem_answer_option_type_enum.create(bind, checkfirst=True)

    if not _has_column("responses", "problem_type_id"):
        op.add_column(
            "responses",
            sa.Column("problem_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _has_column("responses", "answer_option_type"):
        op.add_column(
            "responses",
            sa.Column("answer_option_type", problem_answer_option_type_enum, nullable=True),
        )

    if not _has_column("responses", "difficulty"):
        op.add_column(
            "responses",
            sa.Column("difficulty", difficulty_level_enum, nullable=True),
        )

    if not _has_column("responses", "difficulty_weight"):
        op.add_column(
            "responses",
            sa.Column("difficulty_weight", sa.Float(), nullable=True),
        )


def _assert_known_difficulty_names() -> None:
    bind = op.get_bind()
    unknown_names = bind.execute(
        sa.text(
            """
            SELECT name
            FROM difficulties
            WHERE LOWER(TRIM(name)) NOT IN (
                'very easy',
                'easy',
                'medium',
                'hard',
                'very hard'
            )
            ORDER BY name
            """
        )
    ).scalars().all()
    if unknown_names:
        raise RuntimeError(
            "Cannot migrate difficulties with unknown names: "
            + ", ".join(str(name) for name in unknown_names)
        )


def _backfill_problem_difficulty() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE problems AS p
            SET difficulty = CASE LOWER(TRIM(d.name))
                WHEN 'very easy' THEN 'elementary'::difficulty_level_enum
                WHEN 'easy' THEN 'intermediate'::difficulty_level_enum
                WHEN 'medium' THEN 'upper_intermediate'::difficulty_level_enum
                WHEN 'hard' THEN 'advanced'::difficulty_level_enum
                WHEN 'very hard' THEN 'proficient'::difficulty_level_enum
            END
            FROM difficulties AS d
            WHERE p.difficulty_id = d.id
              AND p.difficulty IS NULL
            """
        )
    )


def _assert_no_missing_problem_difficulty() -> None:
    bind = op.get_bind()
    missing_problem_ids = bind.execute(
        sa.text(
            """
            SELECT id
            FROM problems
            WHERE difficulty IS NULL
            ORDER BY id
            """
        )
    ).scalars().all()
    if missing_problem_ids:
        raise RuntimeError(
            "Cannot finish difficulty migration because some problems do not have a mapped difficulty"
        )


def _backfill_response_snapshots() -> None:
    bind = op.get_bind()
    coefficients = _load_difficulty_coefficients()
    bind.execute(
        sa.text(
            """
            UPDATE responses AS r
            SET problem_type_id = p.problem_type_id,
                answer_option_type = (
                    SELECT pao.type
                    FROM problem_answer_options AS pao
                    WHERE pao.id = r.answer_option_id
                ),
                difficulty = p.difficulty,
                difficulty_weight = CASE p.difficulty::text
                    WHEN 'elementary' THEN :elementary
                    WHEN 'intermediate' THEN :intermediate
                    WHEN 'upper_intermediate' THEN :upper_intermediate
                    WHEN 'advanced' THEN :advanced
                    WHEN 'proficient' THEN :proficient
                    ELSE NULL
                END
            FROM problems AS p
            WHERE r.problem_id = p.id
            """
        ),
        coefficients,
    )


def _backfill_business_config_snapshot() -> None:
    bind = op.get_bind()
    business_config = _load_business_config()
    bind.execute(
        sa.text(
            """
            UPDATE entrance_test_sessions
            SET business_config_snapshot = CAST(:business_config_snapshot AS jsonb)
            WHERE business_config_snapshot IS NULL
            """
        ),
        {"business_config_snapshot": json.dumps(business_config)},
    )


def _restore_legacy_difficulties() -> None:
    bind = op.get_bind()
    business_config = _load_business_config()
    difficulties = _require_business_difficulties(business_config)
    difficulty_rows = bind.execute(
        sa.text("SELECT id, name FROM difficulties")
    ).mappings().all()
    difficulty_ids_by_name = {
        str(row["name"]).strip().lower(): row["id"]
        for row in difficulty_rows
    }

    for enum_name, legacy_name in LEGACY_DIFFICULTY_NAME_MAPPING.items():
        difficulty_config = difficulties[enum_name]
        existing_id = difficulty_ids_by_name.get(legacy_name)
        if existing_id is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO difficulties (id, name, coefficient)
                    VALUES (:id, :name, :coefficient)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "name": legacy_name,
                    "coefficient": _coerce_float(difficulty_config["coefficient"]),
                },
            )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE difficulties
                    SET coefficient = :coefficient
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing_id,
                    "coefficient": _coerce_float(difficulty_config["coefficient"]),
                },
            )


def _backfill_problem_difficulty_id() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE problems AS p
            SET difficulty_id = d.id
            FROM difficulties AS d
            WHERE d.name = CASE p.difficulty::text
                WHEN 'elementary' THEN 'very easy'
                WHEN 'intermediate' THEN 'easy'
                WHEN 'upper_intermediate' THEN 'medium'
                WHEN 'advanced' THEN 'hard'
                WHEN 'proficient' THEN 'very hard'
                ELSE NULL
            END
              AND p.difficulty_id IS NULL
            """
        )
    )


def _load_business_config() -> dict[str, object]:
    config_path = Path(__file__).resolve().parents[4] / "config" / "settings.toml"
    if not config_path.exists():
        raise RuntimeError(f"Missing business config file: {config_path}")

    with config_path.open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    if not isinstance(raw_config, dict):
        raise RuntimeError("Business config must be a TOML object")

    return raw_config


def _load_difficulty_coefficients() -> dict[str, float]:
    business_config = _load_business_config()
    difficulties = _require_business_difficulties(business_config)

    coefficients: dict[str, float] = {}
    for difficulty_name in DIFFICULTY_LEVELS:
        difficulty_config = difficulties.get(difficulty_name)
        if not isinstance(difficulty_config, Mapping):
            raise RuntimeError(f"Missing difficulty config for {difficulty_name}")
        coefficients[difficulty_name] = _coerce_float(difficulty_config["coefficient"])
    return coefficients


def _drop_foreign_keys(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for foreign_key in inspector.get_foreign_keys(table_name):
        constrained_columns = foreign_key.get("constrained_columns") or []
        constraint_name = foreign_key.get("name")
        if column_name in constrained_columns and constraint_name is not None:
            op.drop_constraint(
                constraint_name,
                table_name,
                type_="foreignkey",
            )


def _require_business_difficulties(
    business_config: Mapping[str, object],
) -> Mapping[str, Mapping[str, object]]:
    raw_difficulties = business_config.get("difficulties")
    if not isinstance(raw_difficulties, Mapping):
        raise RuntimeError("Business config must define a [difficulties] table")

    difficulties = cast("Mapping[str, Mapping[str, object]]", raw_difficulties)
    return difficulties


def _coerce_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    raise RuntimeError(f"Expected numeric config value, got {type(value).__name__}")


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)
