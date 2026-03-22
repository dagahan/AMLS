from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from src.config import get_app_config
from src.core.utils import PasswordTools
from src.db.database import DataBase
from src.db.enums import EntranceTestStatus, ProblemAnswerOptionType, UserRole
from src.db.problem_type_tree import build_problem_type_tree_lines, build_problem_type_tree_text
from src.db.reference_dataset import PROBLEM_TYPE_DATA, TOPIC_DATA
from src.db.reference_problem_bank import build_reference_problem_bank, load_reference_problem_bank
from src.db.reference_sync import sync_reference_data
from src.models.alchemy import (
    EntranceTestSession,
    Problem,
    ProblemAnswerOption,
    ProblemType,
    ProblemTypePrerequisite,
    ResponseEvent,
    Subtopic,
    Topic,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_problem_type_tree_contains_every_reference_problem_type_once() -> None:
    lines = build_problem_type_tree_lines(PROBLEM_TYPE_DATA)
    tree_text = build_problem_type_tree_text(PROBLEM_TYPE_DATA)
    stripped_lines = tuple(line.lstrip() for line in lines)
    root_count = sum(1 for _, prerequisite_name in PROBLEM_TYPE_DATA if prerequisite_name is None)

    assert len(lines) == len(PROBLEM_TYPE_DATA)
    assert len(set(stripped_lines)) == len(PROBLEM_TYPE_DATA)
    assert sum(1 for line in lines if not line.startswith("  ")) == root_count
    assert "compare and estimate real numbers" in tree_text
    assert "  compute with fractions and signed numbers" in tree_text
    assert "    convert fractions, decimals, and percentages" in tree_text


def test_reference_problem_bank_builds_two_problems_per_problem_type() -> None:
    generated_problems = build_reference_problem_bank()
    problem_count_by_type = Counter(
        generated_problem["problem_type_name"]
        for generated_problem in generated_problems
    )
    valid_subtopic_keys = {
        (topic_name, subtopic_name)
        for topic_name, subtopic_names in TOPIC_DATA
        for subtopic_name in subtopic_names
    }

    assert len(generated_problems) == len(PROBLEM_TYPE_DATA) * 2
    assert set(problem_count_by_type.values()) == {2}

    for generated_problem in generated_problems:
        answer_option_types = Counter(
            answer_option["type"]
            for answer_option in generated_problem["answer_options"]
        )

        assert answer_option_types[ProblemAnswerOptionType.RIGHT] == 1
        assert answer_option_types[ProblemAnswerOptionType.WRONG] == 1
        assert answer_option_types[ProblemAnswerOptionType.I_DONT_KNOW] == 1
        assert (
            generated_problem["topic_name"],
            generated_problem["subtopic_name"],
        ) in valid_subtopic_keys


@pytest.mark.asyncio
async def test_load_reference_problem_bank_restores_reference_catalog(
    database: DataBase,
) -> None:
    await sync_reference_data(database)
    await load_reference_problem_bank(database)

    async with database.session_ctx() as session:
        topic_count = await _count_rows(session, Topic)
        subtopic_count = await _count_rows(session, Subtopic)
        problem_type_count = await _count_rows(session, ProblemType)
        prerequisite_edge_count = await _count_rows(session, ProblemTypePrerequisite)
        problem_count = await _count_rows(session, Problem)
        answer_option_count = await _count_rows(session, ProblemAnswerOption)

        per_type_rows = await session.execute(
            select(ProblemType.name, func.count(Problem.id))
            .join(Problem, Problem.problem_type_id == ProblemType.id)
            .group_by(ProblemType.name)
        )
        problem_count_by_type = {
            problem_type_name: int(problem_count)
            for problem_type_name, problem_count in per_type_rows.all()
        }

    assert topic_count == 19
    assert subtopic_count == 186
    assert len(get_app_config().list_difficulties()) == 5
    assert problem_type_count == len(PROBLEM_TYPE_DATA)
    assert prerequisite_edge_count == len(PROBLEM_TYPE_DATA) - 8
    assert problem_count == len(PROBLEM_TYPE_DATA) * 2
    assert answer_option_count == len(PROBLEM_TYPE_DATA) * 6
    assert set(problem_count_by_type.values()) == {2}


@pytest.mark.asyncio
async def test_load_reference_problem_bank_resets_sessions_and_deletes_old_responses(
    database: DataBase,
) -> None:
    async with database.session_ctx() as session:
        seeded_problem = (
            await session.execute(select(Problem).order_by(Problem.created_at, Problem.id))
        ).scalars().first()
        assert seeded_problem is not None

        answer_option = (
            await session.execute(
                select(ProblemAnswerOption)
                .where(ProblemAnswerOption.problem_id == seeded_problem.id)
                .order_by(ProblemAnswerOption.id)
            )
        ).scalars().first()
        assert answer_option is not None

        student = User(
            email=f"restore-{uuid.uuid4().hex}@example.org",
            first_name="Restore",
            last_name="Student",
            avatar_url=None,
            hashed_password=PasswordTools.hash_password("Student123!"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(student)
        await session.flush()

        entrance_test_session = EntranceTestSession(
            user_id=student.id,
            status=EntranceTestStatus.ACTIVE,
            structure_version=1,
            current_problem_id=seeded_problem.id,
            final_state_index=3,
            final_state_probability=0.82,
            learned_problem_type_ids=[seeded_problem.problem_type_id],
            inner_fringe_problem_type_ids=[seeded_problem.problem_type_id],
            outer_fringe_problem_type_ids=[seeded_problem.problem_type_id],
            started_at=datetime.now(UTC),
        )
        session.add(entrance_test_session)
        await session.flush()

        response_event = ResponseEvent(
            user_id=student.id,
            problem_id=seeded_problem.id,
            answer_option_id=answer_option.id,
            entrance_test_session_id=entrance_test_session.id,
        )
        session.add(response_event)
        await session.flush()

        entrance_test_session_id = entrance_test_session.id

    await sync_reference_data(database)
    await load_reference_problem_bank(database)

    async with database.session_ctx() as session:
        reloaded_session = await session.get(EntranceTestSession, entrance_test_session_id)
        response_count = await _count_rows(session, ResponseEvent)

    assert reloaded_session is not None
    assert reloaded_session.status == EntranceTestStatus.PENDING
    assert reloaded_session.current_problem_id is None
    assert reloaded_session.started_at is None
    assert reloaded_session.completed_at is None
    assert reloaded_session.skipped_at is None
    assert reloaded_session.final_state_index is None
    assert reloaded_session.final_state_probability is None
    assert reloaded_session.learned_problem_type_ids == []
    assert reloaded_session.inner_fringe_problem_type_ids == []
    assert reloaded_session.outer_fringe_problem_type_ids == []
    assert response_count == 0


async def _count_rows(session: "AsyncSession", model: type[object]) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())
