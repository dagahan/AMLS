from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import Numeric, case, cast, func, literal, select

from src.models.alchemy import Difficulty, Problem, ProblemSkill, ResponseEvent, Skill, Subtopic, Topic, TopicSubtopic
from src.models.pydantic.mastery import (
    MasteryBetaValue,
    MasteryOverviewCache,
    MasteryOverviewResponse,
    MasteryValueResponse,
)
from src.services.mastery.mastery_cache_manager import MasteryCacheManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.selectable import CTE

    from src.db.database import DataBase


class MasteryService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.cache_manager = MasteryCacheManager()
        self.alpha_0 = Decimal("2")
        self.beta_0 = Decimal("2")
        self.numeric_type = Numeric(18, 6)


    async def get_mastery_overview(self, user_id: uuid.UUID) -> MasteryOverviewResponse:
        overview_cache = await self._get_mastery_overview_cache(user_id)
        return self._build_mastery_overview(overview_cache)


    async def get_skill_mastery(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> MasteryValueResponse:
        overview_cache = await self._get_mastery_overview_cache(user_id)
        return self._build_mastery_value_response(
            self._find_beta_value(overview_cache.skills, skill_id, "Skill")
        )


    async def get_subtopic_mastery(self, user_id: uuid.UUID, subtopic_id: uuid.UUID) -> MasteryValueResponse:
        overview_cache = await self._get_mastery_overview_cache(user_id)
        return self._build_mastery_value_response(
            self._find_beta_value(overview_cache.subtopics, subtopic_id, "Subtopic")
        )


    async def get_topic_mastery(self, user_id: uuid.UUID, topic_id: uuid.UUID) -> MasteryValueResponse:
        overview_cache = await self._get_mastery_overview_cache(user_id)
        return self._build_mastery_value_response(
            self._find_beta_value(overview_cache.topics, topic_id, "Topic")
        )


    async def _get_mastery_overview_cache(self, user_id: uuid.UUID) -> MasteryOverviewCache:
        cached_overview = await self.cache_manager.get_mastery_overview(str(user_id))
        if cached_overview is not None:
            return cached_overview

        overview_cache = await self._compute_mastery_overview_cache(user_id)
        await self.cache_manager.set_mastery_overview(str(user_id), overview_cache)
        return overview_cache


    async def _compute_mastery_overview_cache(self, user_id: uuid.UUID) -> MasteryOverviewCache:
        async with self.db.session_ctx() as session:
            latest_responses = self._build_latest_responses_cte(user_id)
            skill_betas = await self._compute_skill_betas(session, latest_responses)
            subtopic_betas = await self._compute_subtopic_betas(session, latest_responses)
            topic_betas = await self._compute_topic_betas(session, subtopic_betas)

        return MasteryOverviewCache(
            skills=skill_betas,
            subtopics=subtopic_betas,
            topics=topic_betas,
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


    async def _compute_skill_betas(
        self,
        session: "AsyncSession",
        latest_responses: "CTE",
    ) -> list[MasteryBetaValue]:
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

        skill_ids_result = await session.execute(select(Skill.id))
        betas_by_skill_id = {
            skill_id: self._build_prior_beta_value(skill_id)
            for skill_id in skill_ids_result.scalars().all()
        }

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

        for skill_id, success_value, failure_value in result.all():
            betas_by_skill_id[skill_id] = self._build_beta_value(
                entity_id=skill_id,
                success_sum=self._to_decimal(success_value),
                failure_sum=self._to_decimal(failure_value),
            )

        return self._sort_beta_values(betas_by_skill_id)


    async def _compute_subtopic_betas(
        self,
        session: "AsyncSession",
        latest_responses: "CTE",
    ) -> list[MasteryBetaValue]:
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

        subtopic_ids_result = await session.execute(select(Subtopic.id))
        betas_by_subtopic_id = {
            subtopic_id: self._build_prior_beta_value(subtopic_id)
            for subtopic_id in subtopic_ids_result.scalars().all()
        }

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

        for subtopic_id, success_value, failure_value in result.all():
            betas_by_subtopic_id[subtopic_id] = self._build_beta_value(
                entity_id=subtopic_id,
                success_sum=self._to_decimal(success_value),
                failure_sum=self._to_decimal(failure_value),
            )

        return self._sort_beta_values(betas_by_subtopic_id)


    async def _compute_topic_betas(
        self,
        session: "AsyncSession",
        subtopic_betas: list[MasteryBetaValue],
    ) -> list[MasteryBetaValue]:
        subtopic_beta_by_id = {item.id: item for item in subtopic_betas}

        topic_ids_result = await session.execute(select(Topic.id))
        topic_ids = list(topic_ids_result.scalars().all())
        explicit_links_result = await session.execute(
            select(TopicSubtopic.topic_id, TopicSubtopic.subtopic_id, TopicSubtopic.weight)
        )
        fallback_links_result = await session.execute(select(Subtopic.topic_id, Subtopic.id))

        explicit_links_by_topic_id: dict[uuid.UUID, list[tuple[uuid.UUID, Decimal]]] = {}
        for topic_id, subtopic_id, weight in explicit_links_result.all():
            explicit_links_by_topic_id.setdefault(topic_id, []).append(
                (subtopic_id, self._to_decimal(weight))
            )

        fallback_links_by_topic_id: dict[uuid.UUID, list[tuple[uuid.UUID, Decimal]]] = {}
        for topic_id, subtopic_id in fallback_links_result.all():
            fallback_links_by_topic_id.setdefault(topic_id, []).append(
                (subtopic_id, Decimal("1"))
            )

        betas_by_topic_id: dict[uuid.UUID, MasteryBetaValue] = {}
        for topic_id in topic_ids:
            links = explicit_links_by_topic_id.get(topic_id)
            if not links:
                links = fallback_links_by_topic_id.get(topic_id, [])

            pooled_success = Decimal("0")
            pooled_failure = Decimal("0")

            for subtopic_id, weight in links:
                subtopic_beta = subtopic_beta_by_id.get(subtopic_id)
                if subtopic_beta is None:
                    subtopic_beta = self._build_prior_beta_value(subtopic_id)

                child_success = max(subtopic_beta.alpha - self.alpha_0, Decimal("0"))
                child_failure = max(subtopic_beta.beta - self.beta_0, Decimal("0"))

                pooled_success += weight * child_success
                pooled_failure += weight * child_failure

            betas_by_topic_id[topic_id] = self._build_beta_value(
                entity_id=topic_id,
                success_sum=pooled_success,
                failure_sum=pooled_failure,
            )

        return self._sort_beta_values(betas_by_topic_id)


    def _build_prior_beta_value(self, entity_id: uuid.UUID) -> MasteryBetaValue:
        return MasteryBetaValue(
            id=entity_id,
            alpha=self.alpha_0,
            beta=self.beta_0,
            mastery=self._posterior_mean(self.alpha_0, self.beta_0),
        )


    def _build_beta_value(
        self,
        entity_id: uuid.UUID,
        success_sum: Decimal,
        failure_sum: Decimal,
    ) -> MasteryBetaValue:
        alpha = self.alpha_0 + success_sum
        beta = self.beta_0 + failure_sum
        return MasteryBetaValue(
            id=entity_id,
            alpha=alpha,
            beta=beta,
            mastery=self._posterior_mean(alpha, beta),
        )


    def _build_mastery_overview(self, overview_cache: MasteryOverviewCache) -> MasteryOverviewResponse:
        return MasteryOverviewResponse(
            skills=self._build_mastery_value_responses(overview_cache.skills),
            subtopics=self._build_mastery_value_responses(overview_cache.subtopics),
            topics=self._build_mastery_value_responses(overview_cache.topics),
        )


    def _build_mastery_value_responses(
        self,
        beta_values: list[MasteryBetaValue],
    ) -> list[MasteryValueResponse]:
        return [
            self._build_mastery_value_response(beta_value)
            for beta_value in beta_values
        ]


    def _build_mastery_value_response(self, beta_value: MasteryBetaValue) -> MasteryValueResponse:
        return MasteryValueResponse(
            id=beta_value.id,
            mastery=float(beta_value.mastery),
        )


    def _posterior_mean(self, alpha: Decimal, beta: Decimal) -> Decimal:
        mastery = alpha / (alpha + beta)
        return min(max(mastery, Decimal("0")), Decimal("1"))


    def _find_beta_value(
        self,
        beta_values: list[MasteryBetaValue],
        entity_id: uuid.UUID,
        entity_name: str,
    ) -> MasteryBetaValue:
        for beta_value in beta_values:
            if beta_value.id == entity_id:
                return beta_value

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} mastery not found",
        )


    def _sort_beta_values(
        self,
        beta_values_by_id: dict[uuid.UUID, MasteryBetaValue],
    ) -> list[MasteryBetaValue]:
        return [
            beta_values_by_id[entity_id]
            for entity_id in sorted(beta_values_by_id, key=str)
        ]


    def _to_decimal(self, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
