from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select

from src.core.utils import EnvTools
from src.db.database import DataBase
from src.db.reference_dataset import DIFFICULTY_DATA, PROBLEM_TYPE_DATA, TOPIC_DATA
from src.models.alchemy import (
    Difficulty,
    Problem,
    ProblemType,
    ProblemTypePrerequisite,
    Subtopic,
    Topic,
    TopicSubtopic,
)
from src.valkey.mastery_cache import MasteryCache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def sync_reference_data(db: DataBase) -> None:
    async with db.session_ctx() as session:
        topic_ids, subtopic_ids, topic_link_ids = await _sync_topics(session)
        problem_type_ids, problem_type_link_ids = await _sync_problem_types(session)
        difficulty_ids = await _sync_difficulties(session)

        await _delete_invalid_problems(
            session=session,
            valid_subtopic_ids=subtopic_ids,
            valid_problem_type_ids=problem_type_ids,
            valid_difficulty_ids=difficulty_ids,
        )
        await _delete_invalid_subtopics(session, subtopic_ids)
        await _delete_invalid_topics(session, topic_ids)
        await _delete_invalid_problem_types(session, problem_type_ids)
        await _delete_invalid_difficulties(session, difficulty_ids)
        await _delete_invalid_problem_type_links(session, problem_type_link_ids)
        await _delete_invalid_topic_links(session, topic_link_ids)

    mastery_cache = MasteryCache()
    await mastery_cache.bump_taxonomy_version()
    await mastery_cache.bump_problem_mapping_version()


async def _sync_topics(
    session: "AsyncSession",
) -> tuple[set[uuid.UUID], set[uuid.UUID], set[tuple[uuid.UUID, uuid.UUID]]]:
    result = await session.execute(select(Topic))
    topics = {topic.name: topic for topic in result.scalars().all()}
    valid_topic_ids: set[uuid.UUID] = set()
    valid_subtopic_ids: set[uuid.UUID] = set()
    valid_topic_link_ids: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for topic_name, subtopic_names in TOPIC_DATA:
        topic = topics.get(topic_name)
        if topic is None:
            topic = Topic(name=topic_name)
            session.add(topic)
            await session.flush()
        valid_topic_ids.add(topic.id)

        subtopic_result = await session.execute(
            select(Subtopic).where(Subtopic.topic_id == topic.id)
        )
        subtopics = {subtopic.name: subtopic for subtopic in subtopic_result.scalars().all()}

        for subtopic_name in subtopic_names:
            subtopic = subtopics.get(subtopic_name)
            if subtopic is None:
                subtopic = Subtopic(topic_id=topic.id, name=subtopic_name)
                session.add(subtopic)
                await session.flush()
            valid_subtopic_ids.add(subtopic.id)
            await _ensure_topic_link(session, topic.id, subtopic.id)
            valid_topic_link_ids.add((topic.id, subtopic.id))

    return valid_topic_ids, valid_subtopic_ids, valid_topic_link_ids


async def _sync_difficulties(session: "AsyncSession") -> set[uuid.UUID]:
    result = await session.execute(select(Difficulty))
    difficulties = {difficulty.name: difficulty for difficulty in result.scalars().all()}
    valid_difficulty_ids: set[uuid.UUID] = set()

    for name, coefficient in DIFFICULTY_DATA:
        difficulty = difficulties.get(name)
        if difficulty is None:
            difficulty = Difficulty(name=name, coefficient=coefficient)
            session.add(difficulty)
            await session.flush()
        else:
            difficulty.coefficient = coefficient
        valid_difficulty_ids.add(difficulty.id)

    return valid_difficulty_ids


async def _sync_problem_types(
    session: "AsyncSession",
) -> tuple[set[uuid.UUID], set[tuple[uuid.UUID, uuid.UUID]]]:
    _validate_problem_type_reference_data()

    result = await session.execute(select(ProblemType))
    problem_types_by_name = {
        problem_type.name: problem_type
        for problem_type in result.scalars().all()
    }
    valid_problem_type_ids: set[uuid.UUID] = set()

    for problem_type_name, _ in PROBLEM_TYPE_DATA:
        problem_type = problem_types_by_name.get(problem_type_name)
        if problem_type is None:
            problem_type = ProblemType(name=problem_type_name)
            session.add(problem_type)
            await session.flush()
            problem_types_by_name[problem_type_name] = problem_type
        valid_problem_type_ids.add(problem_type.id)

    valid_problem_type_link_ids: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for problem_type_name, prerequisite_name in PROBLEM_TYPE_DATA:
        if prerequisite_name is None:
            continue

        problem_type_id = problem_types_by_name[problem_type_name].id
        prerequisite_id = problem_types_by_name[prerequisite_name].id
        await _ensure_problem_type_link(session, problem_type_id, prerequisite_id)
        valid_problem_type_link_ids.add((problem_type_id, prerequisite_id))

    return valid_problem_type_ids, valid_problem_type_link_ids


async def _delete_invalid_problems(
    session: "AsyncSession",
    valid_subtopic_ids: set[uuid.UUID],
    valid_problem_type_ids: set[uuid.UUID],
    valid_difficulty_ids: set[uuid.UUID],
) -> None:
    invalid_problem_ids: set[uuid.UUID] = set()

    problem_result = await session.execute(
        select(Problem.id).where(
            or_(
                ~Problem.subtopic_id.in_(valid_subtopic_ids),
                ~Problem.problem_type_id.in_(valid_problem_type_ids),
                ~Problem.difficulty_id.in_(valid_difficulty_ids),
            )
        )
    )
    invalid_problem_ids.update(problem_result.scalars().all())

    if invalid_problem_ids:
        await session.execute(delete(Problem).where(Problem.id.in_(invalid_problem_ids)))


async def _delete_invalid_subtopics(
    session: "AsyncSession",
    valid_subtopic_ids: set[uuid.UUID],
) -> None:
    await session.execute(delete(Subtopic).where(~Subtopic.id.in_(valid_subtopic_ids)))


async def _delete_invalid_topics(session: "AsyncSession", valid_topic_ids: set[uuid.UUID]) -> None:
    await session.execute(delete(Topic).where(~Topic.id.in_(valid_topic_ids)))


async def _delete_invalid_difficulties(
    session: "AsyncSession",
    valid_difficulty_ids: set[uuid.UUID],
) -> None:
    await session.execute(delete(Difficulty).where(~Difficulty.id.in_(valid_difficulty_ids)))


async def _delete_invalid_problem_types(
    session: "AsyncSession",
    valid_problem_type_ids: set[uuid.UUID],
) -> None:
    await session.execute(delete(ProblemType).where(~ProblemType.id.in_(valid_problem_type_ids)))


async def _delete_invalid_problem_type_links(
    session: "AsyncSession",
    valid_problem_type_link_ids: set[tuple[uuid.UUID, uuid.UUID]],
) -> None:
    result = await session.execute(
        select(
            ProblemTypePrerequisite.problem_type_id,
            ProblemTypePrerequisite.prerequisite_problem_type_id,
        )
    )
    for problem_type_id, prerequisite_problem_type_id in result.all():
        if (problem_type_id, prerequisite_problem_type_id) not in valid_problem_type_link_ids:
            await session.execute(
                delete(ProblemTypePrerequisite).where(
                    ProblemTypePrerequisite.problem_type_id == problem_type_id,
                    ProblemTypePrerequisite.prerequisite_problem_type_id
                    == prerequisite_problem_type_id,
                )
            )


async def _delete_invalid_topic_links(
    session: "AsyncSession",
    valid_topic_link_ids: set[tuple[uuid.UUID, uuid.UUID]],
) -> None:
    result = await session.execute(select(TopicSubtopic.topic_id, TopicSubtopic.subtopic_id))
    for topic_id, subtopic_id in result.all():
        if (topic_id, subtopic_id) not in valid_topic_link_ids:
            await session.execute(
                delete(TopicSubtopic).where(
                    TopicSubtopic.topic_id == topic_id,
                    TopicSubtopic.subtopic_id == subtopic_id,
                )
            )


async def _ensure_topic_link(
    session: "AsyncSession",
    topic_id: uuid.UUID,
    subtopic_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(TopicSubtopic).where(
            TopicSubtopic.topic_id == topic_id,
            TopicSubtopic.subtopic_id == subtopic_id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(TopicSubtopic(topic_id=topic_id, subtopic_id=subtopic_id, weight=1.0))


async def _ensure_problem_type_link(
    session: "AsyncSession",
    problem_type_id: uuid.UUID,
    prerequisite_problem_type_id: uuid.UUID,
) -> None:
    result = await session.execute(
        select(ProblemTypePrerequisite).where(
            ProblemTypePrerequisite.problem_type_id == problem_type_id,
            ProblemTypePrerequisite.prerequisite_problem_type_id == prerequisite_problem_type_id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(
            ProblemTypePrerequisite(
                problem_type_id=problem_type_id,
                prerequisite_problem_type_id=prerequisite_problem_type_id,
            )
        )


def _validate_problem_type_reference_data() -> None:
    problem_type_names = [problem_type_name for problem_type_name, _ in PROBLEM_TYPE_DATA]
    if len(problem_type_names) != len(set(problem_type_names)):
        raise ValueError("Problem type reference data contains duplicate names")

    available_problem_type_names = set(problem_type_names)
    prerequisites_by_problem_type: dict[str, str | None] = {}

    for problem_type_name, prerequisite_name in PROBLEM_TYPE_DATA:
        if prerequisite_name is not None and prerequisite_name not in available_problem_type_names:
            raise ValueError(
                f"Problem type prerequisite '{prerequisite_name}' is not defined"
            )
        prerequisites_by_problem_type[problem_type_name] = prerequisite_name

    active_problem_type_names: set[str] = set()
    visited_problem_type_names: set[str] = set()

    def visit(problem_type_name: str) -> None:
        if problem_type_name in active_problem_type_names:
            raise ValueError("Problem type reference data contains cycles")

        if problem_type_name in visited_problem_type_names:
            return

        active_problem_type_names.add(problem_type_name)
        prerequisite_name = prerequisites_by_problem_type.get(problem_type_name)
        if prerequisite_name is not None:
            visit(prerequisite_name)
        active_problem_type_names.remove(problem_type_name)
        visited_problem_type_names.add(problem_type_name)

    for problem_type_name in problem_type_names:
        visit(problem_type_name)


async def main() -> None:
    EnvTools.bootstrap_env()
    db = DataBase()
    await db.init_alchemy_engine()
    try:
        await sync_reference_data(db)
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
