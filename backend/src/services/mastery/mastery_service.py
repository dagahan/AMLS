from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from src.math_models import build_mastery_overview_cache
from src.models.pydantic.mastery import (
    MasteryBetaValue,
    MasteryOverviewCache,
    MasteryOverviewResponse,
    MasteryValueResponse,
)
from src.services.mastery.mastery_aggregator import MasteryAggregator
from src.valkey.mastery_cache import MasteryCache

if TYPE_CHECKING:
    from src.db.database import DataBase


class MasteryService:
    def __init__(self, db: "DataBase") -> None:
        self.mastery_aggregator = MasteryAggregator(db)
        self.mastery_cache = MasteryCache()
        self.alpha_0 = Decimal("2")
        self.beta_0 = Decimal("2")


    async def get_mastery_overview(self, user_id: uuid.UUID) -> MasteryOverviewResponse:
        overview_cache = await self._get_mastery_overview_cache(user_id)
        return self._build_mastery_overview_response(overview_cache)


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
        cached_overview = await self.mastery_cache.get_mastery_overview(str(user_id))
        if cached_overview is not None:
            return cached_overview

        aggregation_snapshot = await self.mastery_aggregator.build_mastery_snapshot(user_id)
        overview_cache = build_mastery_overview_cache(
            snapshot=aggregation_snapshot,
            alpha_0=self.alpha_0,
            beta_0=self.beta_0,
        )
        await self.mastery_cache.set_mastery_overview(str(user_id), overview_cache)
        return overview_cache


    def _build_mastery_overview_response(
        self,
        overview_cache: MasteryOverviewCache,
    ) -> MasteryOverviewResponse:
        return MasteryOverviewResponse(
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
