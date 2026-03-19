from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from src.fast_api.routers.auth_router import build_current_user_dependency
from src.models.pydantic import (
    MasteryOverviewResponse,
    MasteryValueResponse,
    ResponseCreate,
    ResponseCreateResponse,
)
from src.services.mastery import MasteryService, ResponseService

if TYPE_CHECKING:
    from src.db.database import DataBase
    from src.models.alchemy import User


def get_mastery_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    current_user = build_current_user_dependency(db)
    mastery_service = MasteryService(db)
    response_service = ResponseService(db)


    @router.post("/responses", response_model=ResponseCreateResponse, status_code=201)
    async def create_response(
        data: ResponseCreate,
        user: "User" = Depends(current_user),
    ) -> ResponseCreateResponse:
        return await response_service.create_response(user.id, data)


    @router.get("/mastery/overview", response_model=MasteryOverviewResponse, status_code=200)
    async def get_mastery_overview(
        user: "User" = Depends(current_user),
    ) -> MasteryOverviewResponse:
        return await mastery_service.get_mastery_overview(user.id)


    @router.get("/mastery/skills/{skill_id}", response_model=MasteryValueResponse, status_code=200)
    async def get_skill_mastery(
        skill_id: uuid.UUID,
        user: "User" = Depends(current_user),
    ) -> MasteryValueResponse:
        return await mastery_service.get_skill_mastery(user.id, skill_id)


    @router.get(
        "/mastery/subtopics/{subtopic_id}",
        response_model=MasteryValueResponse,
        status_code=200,
    )
    async def get_subtopic_mastery(
        subtopic_id: uuid.UUID,
        user: "User" = Depends(current_user),
    ) -> MasteryValueResponse:
        return await mastery_service.get_subtopic_mastery(user.id, subtopic_id)


    @router.get("/mastery/topics/{topic_id}", response_model=MasteryValueResponse, status_code=200)
    async def get_topic_mastery(
        topic_id: uuid.UUID,
        user: "User" = Depends(current_user),
    ) -> MasteryValueResponse:
        return await mastery_service.get_topic_mastery(user.id, topic_id)


    return router
