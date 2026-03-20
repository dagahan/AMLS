from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import (
    AuthContext,
    MasteryOverviewResponse,
    MasteryValueResponse,
    ResponseCreate,
    ResponseCreateResponse,
)
from src.services.mastery import MasteryService, ResponseService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_mastery_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    mastery_service = MasteryService(db)
    response_service = ResponseService(db)


    @router.post("/responses", response_model=ResponseCreateResponse, status_code=201)
    async def create_response(
        data: ResponseCreate,
        auth: AuthContext = Depends(require_role()),
    ) -> ResponseCreateResponse:
        return await response_service.create_response(auth.user.id, data)


    @router.get("/mastery/overview", response_model=MasteryOverviewResponse, status_code=200)
    async def get_mastery_overview(
        auth: AuthContext = Depends(require_role()),
    ) -> MasteryOverviewResponse:
        return await mastery_service.get_mastery_overview(auth.user.id)


    @router.get(
        "/mastery/subtopics/{subtopic_id}",
        response_model=MasteryValueResponse,
        status_code=200,
    )
    async def get_subtopic_mastery(
        subtopic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> MasteryValueResponse:
        return await mastery_service.get_subtopic_mastery(auth.user.id, subtopic_id)


    @router.get("/mastery/topics/{topic_id}", response_model=MasteryValueResponse, status_code=200)
    async def get_topic_mastery(
        topic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> MasteryValueResponse:
        return await mastery_service.get_topic_mastery(auth.user.id, topic_id)


    return router
