from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select

from src.core.utils import EnvTools
from src.db.database import DataBase
from src.db.reference_dataset import DIFFICULTY_DATA, SKILL_DATA, TOPIC_DATA
from src.models.alchemy import Difficulty, Problem, ProblemSkill, Skill, Subtopic, Topic, TopicSubtopic
from src.valkey.mastery_cache import MasteryCache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def sync_reference_data(db: DataBase) -> None:
    async with db.session_ctx() as session:
        topic_ids, subtopic_ids, topic_link_ids = await _sync_topics(session)
        skill_ids = await _sync_skills(session)
        difficulty_ids = await _sync_difficulties(session)

        await _delete_invalid_problems(
            session=session,
            valid_subtopic_ids=subtopic_ids,
            valid_skill_ids=skill_ids,
            valid_difficulty_ids=difficulty_ids,
        )
        await _delete_invalid_subtopics(session, subtopic_ids)
        await _delete_invalid_topics(session, topic_ids)
        await _delete_invalid_skills(session, skill_ids)
        await _delete_invalid_difficulties(session, difficulty_ids)
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


async def _sync_skills(session: "AsyncSession") -> set[uuid.UUID]:
    result = await session.execute(select(Skill))
    skills = {skill.name: skill for skill in result.scalars().all()}
    valid_skill_ids: set[uuid.UUID] = set()

    for skill_name in SKILL_DATA:
        skill = skills.get(skill_name)
        if skill is None:
            skill = Skill(name=skill_name)
            session.add(skill)
            await session.flush()
        valid_skill_ids.add(skill.id)

    return valid_skill_ids


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


async def _delete_invalid_problems(
    session: "AsyncSession",
    valid_subtopic_ids: set[uuid.UUID],
    valid_skill_ids: set[uuid.UUID],
    valid_difficulty_ids: set[uuid.UUID],
) -> None:
    invalid_problem_ids: set[uuid.UUID] = set()

    problem_result = await session.execute(
        select(Problem.id).where(
            or_(
                ~Problem.subtopic_id.in_(valid_subtopic_ids),
                ~Problem.difficulty_id.in_(valid_difficulty_ids),
            )
        )
    )
    invalid_problem_ids.update(problem_result.scalars().all())

    link_result = await session.execute(
        select(ProblemSkill.problem_id).where(
            ~ProblemSkill.skill_id.in_(valid_skill_ids)
        )
    )
    invalid_problem_ids.update(link_result.scalars().all())

    if invalid_problem_ids:
        await session.execute(delete(Problem).where(Problem.id.in_(invalid_problem_ids)))


async def _delete_invalid_subtopics(
    session: "AsyncSession",
    valid_subtopic_ids: set[uuid.UUID],
) -> None:
    await session.execute(delete(Subtopic).where(~Subtopic.id.in_(valid_subtopic_ids)))


async def _delete_invalid_topics(session: "AsyncSession", valid_topic_ids: set[uuid.UUID]) -> None:
    await session.execute(delete(Topic).where(~Topic.id.in_(valid_topic_ids)))


async def _delete_invalid_skills(session: "AsyncSession", valid_skill_ids: set[uuid.UUID]) -> None:
    await session.execute(delete(Skill).where(~Skill.id.in_(valid_skill_ids)))


async def _delete_invalid_difficulties(
    session: "AsyncSession",
    valid_difficulty_ids: set[uuid.UUID],
) -> None:
    await session.execute(delete(Difficulty).where(~Difficulty.id.in_(valid_difficulty_ids)))


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
