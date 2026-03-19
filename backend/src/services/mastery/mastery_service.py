from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import case, func, select

from src.models.alchemy import (
    Difficulty,
    Problem,
    ProblemSubskill,
    ResponseEvent,
    Skill,
    SkillSubskill,
    Subskill,
    Subtopic,
    Topic,
    TopicSubtopic,
)
from src.models.pydantic.mastery import MasteryOverviewResponse, MasteryValueResponse
from src.services.mastery.mastery_cache_manager import MasteryCacheManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class MasteryService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.cache_manager = MasteryCacheManager()
        self.alpha_0 = Decimal("2")
        self.beta_0 = Decimal("2")
        self.default_mastery = 0.5


    async def get_mastery_overview(self, user_id: uuid.UUID) -> MasteryOverviewResponse:
        cached_overview = await self.cache_manager.get_mastery_overview(str(user_id))
        if cached_overview is not None:
            return cached_overview

        overview = await self._compute_mastery_overview(user_id)
        await self.cache_manager.set_mastery_overview(str(user_id), overview)
        return overview


    async def get_subskill_mastery(self, user_id: uuid.UUID, subskill_id: uuid.UUID) -> MasteryValueResponse:
        overview = await self.get_mastery_overview(user_id)
        return self._find_mastery_value(overview.subskills, subskill_id, "Subskill")


    async def get_skill_mastery(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> MasteryValueResponse:
        overview = await self.get_mastery_overview(user_id)
        return self._find_mastery_value(overview.skills, skill_id, "Skill")


    async def get_subtopic_mastery(self, user_id: uuid.UUID, subtopic_id: uuid.UUID) -> MasteryValueResponse:
        overview = await self.get_mastery_overview(user_id)
        return self._find_mastery_value(overview.subtopics, subtopic_id, "Subtopic")


    async def get_topic_mastery(self, user_id: uuid.UUID, topic_id: uuid.UUID) -> MasteryValueResponse:
        overview = await self.get_mastery_overview(user_id)
        return self._find_mastery_value(overview.topics, topic_id, "Topic")


    async def _compute_mastery_overview(self, user_id: uuid.UUID) -> MasteryOverviewResponse:
        async with self.db.session_ctx() as session:
            subskill_masteries = await self._compute_subskill_masteries(session, user_id)
            subtopic_masteries = await self._compute_subtopic_masteries(session, user_id)
            skill_masteries = await self._compute_skill_masteries(session, subskill_masteries)
            topic_masteries = await self._compute_topic_masteries(session, subtopic_masteries)

        return MasteryOverviewResponse(
            subskills=subskill_masteries,
            skills=skill_masteries,
            subtopics=subtopic_masteries,
            topics=topic_masteries,
        )


    async def _compute_subskill_masteries(
        self,
        session: "AsyncSession",
        user_id: uuid.UUID,
    ) -> list[MasteryValueResponse]:
        weighted_value = ProblemSubskill.weight * Difficulty.coefficient
        success_evidence = func.coalesce(
            func.sum(
                case(
                    (ResponseEvent.is_correct.is_(True), weighted_value),
                    else_=0.0,
                )
            ),
            0.0,
        )
        failure_evidence = func.coalesce(
            func.sum(
                case(
                    (ResponseEvent.is_correct.is_(False), weighted_value),
                    else_=0.0,
                )
            ),
            0.0,
        )

        all_subskills_result = await session.execute(select(Subskill.id))
        mastery_by_subskill_id = {
            subskill_id: self.default_mastery
            for subskill_id in all_subskills_result.scalars().all()
        }

        result = await session.execute(
            select(
                ProblemSubskill.subskill_id,
                success_evidence.label("success_evidence"),
                failure_evidence.label("failure_evidence"),
            )
            .select_from(ResponseEvent)
            .join(Problem, Problem.id == ResponseEvent.problem_id)
            .join(Difficulty, Difficulty.id == Problem.difficulty_id)
            .join(ProblemSubskill, ProblemSubskill.problem_id == Problem.id)
            .where(ResponseEvent.user_id == user_id)
            .group_by(ProblemSubskill.subskill_id)
        )

        for subskill_id, success_value, failure_value in result.all():
            mastery_by_subskill_id[subskill_id] = self._calculate_posterior_mean(
                success_value,
                failure_value,
            )

        return self._build_sorted_mastery_values(mastery_by_subskill_id)


    async def _compute_subtopic_masteries(
        self,
        session: "AsyncSession",
        user_id: uuid.UUID,
    ) -> list[MasteryValueResponse]:
        success_evidence = func.coalesce(
            func.sum(
                case(
                    (ResponseEvent.is_correct.is_(True), Difficulty.coefficient),
                    else_=0.0,
                )
            ),
            0.0,
        )
        failure_evidence = func.coalesce(
            func.sum(
                case(
                    (ResponseEvent.is_correct.is_(False), Difficulty.coefficient),
                    else_=0.0,
                )
            ),
            0.0,
        )

        all_subtopics_result = await session.execute(select(Subtopic.id))
        mastery_by_subtopic_id = {
            subtopic_id: self.default_mastery
            for subtopic_id in all_subtopics_result.scalars().all()
        }

        result = await session.execute(
            select(
                Problem.subtopic_id,
                success_evidence.label("success_evidence"),
                failure_evidence.label("failure_evidence"),
            )
            .select_from(ResponseEvent)
            .join(Problem, Problem.id == ResponseEvent.problem_id)
            .join(Difficulty, Difficulty.id == Problem.difficulty_id)
            .where(ResponseEvent.user_id == user_id)
            .group_by(Problem.subtopic_id)
        )

        for subtopic_id, success_value, failure_value in result.all():
            mastery_by_subtopic_id[subtopic_id] = self._calculate_posterior_mean(
                success_value,
                failure_value,
            )

        return self._build_sorted_mastery_values(mastery_by_subtopic_id)


    async def _compute_skill_masteries(
        self,
        session: "AsyncSession",
        subskill_masteries: list[MasteryValueResponse],
    ) -> list[MasteryValueResponse]:
        mastery_by_subskill_id = {item.id: item.mastery for item in subskill_masteries}
        skill_ids_result = await session.execute(select(Skill.id))
        skill_ids = list(skill_ids_result.scalars().all())
        explicit_links = await session.execute(
            select(SkillSubskill.skill_id, SkillSubskill.subskill_id, SkillSubskill.weight)
        )
        fallback_links = await session.execute(select(Subskill.skill_id, Subskill.id))

        explicit_links_by_skill_id: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {}
        for skill_id, subskill_id, weight in explicit_links.all():
            explicit_links_by_skill_id.setdefault(skill_id, []).append((subskill_id, weight))

        fallback_links_by_skill_id: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {}
        for skill_id, subskill_id in fallback_links.all():
            fallback_links_by_skill_id.setdefault(skill_id, []).append((subskill_id, 1.0))

        mastery_by_skill_id: dict[uuid.UUID, float] = {}
        for skill_id in skill_ids:
            links = explicit_links_by_skill_id.get(skill_id)
            if not links:
                links = fallback_links_by_skill_id.get(skill_id, [])
            mastery_by_skill_id[skill_id] = self._calculate_weighted_average(
                links,
                mastery_by_subskill_id,
            )

        return self._build_sorted_mastery_values(mastery_by_skill_id)


    async def _compute_topic_masteries(
        self,
        session: "AsyncSession",
        subtopic_masteries: list[MasteryValueResponse],
    ) -> list[MasteryValueResponse]:
        mastery_by_subtopic_id = {item.id: item.mastery for item in subtopic_masteries}
        topic_ids_result = await session.execute(select(Topic.id))
        topic_ids = list(topic_ids_result.scalars().all())
        explicit_links = await session.execute(
            select(TopicSubtopic.topic_id, TopicSubtopic.subtopic_id, TopicSubtopic.weight)
        )
        fallback_links = await session.execute(select(Subtopic.topic_id, Subtopic.id))

        explicit_links_by_topic_id: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {}
        for topic_id, subtopic_id, weight in explicit_links.all():
            explicit_links_by_topic_id.setdefault(topic_id, []).append((subtopic_id, weight))

        fallback_links_by_topic_id: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {}
        for topic_id, subtopic_id in fallback_links.all():
            fallback_links_by_topic_id.setdefault(topic_id, []).append((subtopic_id, 1.0))

        mastery_by_topic_id: dict[uuid.UUID, float] = {}
        for topic_id in topic_ids:
            links = explicit_links_by_topic_id.get(topic_id)
            if not links:
                links = fallback_links_by_topic_id.get(topic_id, [])
            mastery_by_topic_id[topic_id] = self._calculate_weighted_average(
                links,
                mastery_by_subtopic_id,
            )

        return self._build_sorted_mastery_values(mastery_by_topic_id)


    def _calculate_posterior_mean(
        self,
        success_evidence: float,
        failure_evidence: float,
    ) -> float:
        alpha = self.alpha_0 + Decimal(str(success_evidence))
        beta = self.beta_0 + Decimal(str(failure_evidence))
        return self._clamp_mastery(alpha / (alpha + beta))


    def _calculate_weighted_average(
        self,
        links: list[tuple[uuid.UUID, float]],
        mastery_by_child_id: dict[uuid.UUID, float],
    ) -> float:
        if not links:
            return self.default_mastery

        weighted_sum = Decimal("0")
        total_weight = Decimal("0")

        for child_id, weight in links:
            decimal_weight = Decimal(str(weight))
            weighted_sum += decimal_weight * Decimal(str(mastery_by_child_id.get(child_id, self.default_mastery)))
            total_weight += decimal_weight

        if total_weight == 0:
            return self.default_mastery

        return self._clamp_mastery(weighted_sum / total_weight)


    def _clamp_mastery(self, value: Decimal) -> float:
        clamped_value = min(max(value, Decimal("0")), Decimal("1"))
        return float(clamped_value)


    def _build_sorted_mastery_values(
        self,
        mastery_by_entity_id: dict[uuid.UUID, float],
    ) -> list[MasteryValueResponse]:
        return [
            MasteryValueResponse(id=entity_id, mastery=mastery_by_entity_id[entity_id])
            for entity_id in sorted(mastery_by_entity_id, key=str)
        ]


    def _find_mastery_value(
        self,
        mastery_values: list[MasteryValueResponse],
        entity_id: uuid.UUID,
        entity_name: str,
    ) -> MasteryValueResponse:
        for mastery_value in mastery_values:
            if mastery_value.id == entity_id:
                return mastery_value

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_name} mastery not found",
        )
