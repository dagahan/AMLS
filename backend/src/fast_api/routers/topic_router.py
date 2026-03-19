from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from src.db.enums import UserRole
from src.fast_api.dependencies import parse_optional_uuid, require_role
from src.models.pydantic import (
    AuthContext,
    MessageResponse,
    SubtopicCreate,
    SubtopicResponse,
    SubtopicUpdate,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)
from src.services.catalog import TopicService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_topic_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    topic_service = TopicService(db)


    @router.get("/topics", response_model=list[TopicResponse], status_code=200)
    async def list_topics(
        auth: AuthContext = Depends(require_role()),
    ) -> list[TopicResponse]:
        return await topic_service.list_topics()


    @router.get("/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def get_topic(
        topic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> TopicResponse:
        return await topic_service.get_topic(topic_id)


    @router.get("/subtopics", response_model=list[SubtopicResponse], status_code=200)
    async def list_subtopics(
        topic_id: str | None = Query(default=None),
        auth: AuthContext = Depends(require_role()),
    ) -> list[SubtopicResponse]:
        return await topic_service.list_subtopics(parse_optional_uuid(topic_id, "topic_id"))


    @router.get("/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def get_subtopic(
        subtopic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> SubtopicResponse:
        return await topic_service.get_subtopic(subtopic_id)


    @router.post("/admin/topics", response_model=TopicResponse, status_code=201)
    async def create_topic(
        data: TopicCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> TopicResponse:
        return await topic_service.create_topic(data)


    @router.get("/admin/topics", response_model=list[TopicResponse], status_code=200)
    async def list_admin_topics(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[TopicResponse]:
        return await topic_service.list_topics()


    @router.get("/admin/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def get_admin_topic(
        topic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> TopicResponse:
        return await topic_service.get_topic(topic_id)


    @router.patch("/admin/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def update_topic(
        topic_id: uuid.UUID,
        data: TopicUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> TopicResponse:
        return await topic_service.update_topic(topic_id, data)


    @router.delete("/admin/topics/{topic_id}", response_model=MessageResponse, status_code=200)
    async def delete_topic(
        topic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        await topic_service.delete_topic(topic_id)
        return MessageResponse(message="Topic deleted")


    @router.post("/admin/subtopics", response_model=SubtopicResponse, status_code=201)
    async def create_subtopic(
        data: SubtopicCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SubtopicResponse:
        return await topic_service.create_subtopic(data)


    @router.get("/admin/subtopics", response_model=list[SubtopicResponse], status_code=200)
    async def list_admin_subtopics(
        topic_id: str | None = Query(default=None),
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[SubtopicResponse]:
        return await topic_service.list_subtopics(parse_optional_uuid(topic_id, "topic_id"))


    @router.get("/admin/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def get_admin_subtopic(
        subtopic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SubtopicResponse:
        return await topic_service.get_subtopic(subtopic_id)


    @router.patch("/admin/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def update_subtopic(
        subtopic_id: uuid.UUID,
        data: SubtopicUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SubtopicResponse:
        return await topic_service.update_subtopic(subtopic_id, data)


    @router.delete("/admin/subtopics/{subtopic_id}", response_model=MessageResponse, status_code=200)
    async def delete_subtopic(
        subtopic_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        await topic_service.delete_subtopic(subtopic_id)
        return MessageResponse(message="Subtopic deleted")


    return router
