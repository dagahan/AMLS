from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Numeric, case, cast, func, literal, select

from src.models.alchemy import (
    Difficulty,
    Problem,
    ProblemSkill,
    ResponseEvent,
    Skill,
    Subtopic,
    Topic,
    TopicSubtopic,
)
from src.models.pydantic.mastery import (
    MasteryAggregationSnapshot,
    MasteryEvidenceValue,
    TopicSubtopicWeightValue,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.selectable import CTE

    from src.db.database import DataBase


class MasteryAggregator:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.numeric_type = Numeric(18, 6)


    async def build_mastery_snapshot(self, user_id: uuid.UUID) -> MasteryAggregationSnapshot:
        async with self.db.session_ctx() as session:
            latest_responses = self._build_latest_responses_cte(user_id)
            return MasteryAggregationSnapshot(
                skill_ids=await self._load_skill_ids(session),
                subtopic_ids=await self._load_subtopic_ids(session),
                topic_ids=await self._load_topic_ids(session),
                skill_evidence=await self._load_skill_evidence(session, latest_responses),
                subtopic_evidence=await self._load_subtopic_evidence(session, latest_responses),
                topic_links=await self._load_topic_links(session),
            )


    def _build_latest_responses_cte(self, user_id: uuid.UUID) -> "CTE":
        response_rank = func.row_number().over(
            partition_by=(ResponseEvent.user_id, ResponseEvent.problem_id),
            order_by=(ResponseEvent.created_at.desc(), ResponseEvent.id.desc()),
        )

        ranked_responses = (
            select(
                ResponseEvent.problem_id.label("problem_id"),
                ResponseEvent.is_correct.label("is_correct"),
                response_rank.label("response_rank"),
            )
            .where(ResponseEvent.user_id == user_id)
            .cte("ranked_responses")
        )

        return (
            select(
                ranked_responses.c.problem_id,
                ranked_responses.c.is_correct,
            )
            .where(ranked_responses.c.response_rank == 1)
            .cte("latest_responses")
        )


    async def _load_skill_ids(self, session: "AsyncSession") -> list[uuid.UUID]:
        result = await session.execute(select(Skill.id))
        return list(result.scalars().all())


    async def _load_subtopic_ids(self, session: "AsyncSession") -> list[uuid.UUID]:
        result = await session.execute(select(Subtopic.id))
        return list(result.scalars().all())


    async def _load_topic_ids(self, session: "AsyncSession") -> list[uuid.UUID]:
        result = await session.execute(select(Topic.id))
        return list(result.scalars().all())


    async def _load_skill_evidence(
        self,
        session: "AsyncSession",
        latest_responses: "CTE",
    ) -> list[MasteryEvidenceValue]:
        weighted_value = cast(ProblemSkill.weight, self.numeric_type) * cast(
            Difficulty.coefficient,
            self.numeric_type,
        )
        success_sum = func.coalesce(
            func.sum(
                case(
                    (latest_responses.c.is_correct.is_(True), weighted_value),
                    else_=cast(literal(0), self.numeric_type),
                )
            ),
            cast(literal(0), self.numeric_type),
        )
        failure_sum = func.coalesce(
            func.sum(
                case(
                    (latest_responses.c.is_correct.is_(False), weighted_value),
                    else_=cast(literal(0), self.numeric_type),
                )
            ),
            cast(literal(0), self.numeric_type),
        )

        result = await session.execute(
            select(
                ProblemSkill.skill_id,
                success_sum.label("success_sum"),
                failure_sum.label("failure_sum"),
            )
            .select_from(latest_responses)
            .join(Problem, Problem.id == latest_responses.c.problem_id)
            .join(Difficulty, Difficulty.id == Problem.difficulty_id)
            .join(ProblemSkill, ProblemSkill.problem_id == Problem.id)
            .group_by(ProblemSkill.skill_id)
        )

        return [
            MasteryEvidenceValue(
                id=skill_id,
                success_sum=self._to_decimal(success_value),
                failure_sum=self._to_decimal(failure_value),
            )
            for skill_id, success_value, failure_value in result.all()
        ]


    async def _load_subtopic_evidence(
        self,
        session: "AsyncSession",
        latest_responses: "CTE",
    ) -> list[MasteryEvidenceValue]:
        difficulty_value = cast(Difficulty.coefficient, self.numeric_type)
        success_sum = func.coalesce(
            func.sum(
                case(
                    (latest_responses.c.is_correct.is_(True), difficulty_value),
                    else_=cast(literal(0), self.numeric_type),
                )
            ),
            cast(literal(0), self.numeric_type),
        )
        failure_sum = func.coalesce(
            func.sum(
                case(
                    (latest_responses.c.is_correct.is_(False), difficulty_value),
                    else_=cast(literal(0), self.numeric_type),
                )
            ),
            cast(literal(0), self.numeric_type),
        )

        result = await session.execute(
            select(
                Problem.subtopic_id,
                success_sum.label("success_sum"),
                failure_sum.label("failure_sum"),
            )
            .select_from(latest_responses)
            .join(Problem, Problem.id == latest_responses.c.problem_id)
            .join(Difficulty, Difficulty.id == Problem.difficulty_id)
            .group_by(Problem.subtopic_id)
        )

        return [
            MasteryEvidenceValue(
                id=subtopic_id,
                success_sum=self._to_decimal(success_value),
                failure_sum=self._to_decimal(failure_value),
            )
            for subtopic_id, success_value, failure_value in result.all()
        ]


    async def _load_topic_links(self, session: "AsyncSession") -> list[TopicSubtopicWeightValue]:
        explicit_links_result = await session.execute(
            select(TopicSubtopic.topic_id, TopicSubtopic.subtopic_id, TopicSubtopic.weight)
        )
        fallback_links_result = await session.execute(select(Subtopic.topic_id, Subtopic.id))
        topic_ids = await self._load_topic_ids(session)

        explicit_links_by_topic_id: dict[uuid.UUID, list[TopicSubtopicWeightValue]] = {}
        for topic_id, subtopic_id, weight in explicit_links_result.all():
            explicit_links_by_topic_id.setdefault(topic_id, []).append(
                TopicSubtopicWeightValue(
                    topic_id=topic_id,
                    subtopic_id=subtopic_id,
                    weight=self._to_decimal(weight),
                )
            )

        fallback_links_by_topic_id: dict[uuid.UUID, list[TopicSubtopicWeightValue]] = {}
        for topic_id, subtopic_id in fallback_links_result.all():
            fallback_links_by_topic_id.setdefault(topic_id, []).append(
                TopicSubtopicWeightValue(
                    topic_id=topic_id,
                    subtopic_id=subtopic_id,
                    weight=Decimal("1"),
                )
            )

        resolved_links: list[TopicSubtopicWeightValue] = []
        for topic_id in topic_ids:
            topic_links = explicit_links_by_topic_id.get(topic_id)
            if topic_links:
                resolved_links.extend(topic_links)
                continue
            resolved_links.extend(fallback_links_by_topic_id.get(topic_id, []))

        return resolved_links


    def _to_decimal(self, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
