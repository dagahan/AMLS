from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select

from src.models.alchemy import Subtopic, Topic, TopicSubtopic
from src.fast_api.routers.auth_router import build_current_admin_dependency, parse_optional_uuid
from src.models.pydantic import (
    MessageResponse,
    SubtopicCreate,
    SubtopicResponse,
    SubtopicUpdate,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)
from src.services.mastery.mastery_cache_manager import MasteryCacheManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.models.alchemy import User


def get_topic_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    current_admin = build_current_admin_dependency(db)
    mastery_cache_manager = MasteryCacheManager()


    async def get_topic_or_404(session: "AsyncSession", topic_id: uuid.UUID) -> Topic:
        result = await session.execute(select(Topic).where(Topic.id == topic_id))
        topic = result.scalar_one_or_none()
        if topic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
        return topic


    async def get_subtopic_or_404(session: "AsyncSession", subtopic_id: uuid.UUID) -> Subtopic:
        result = await session.execute(select(Subtopic).where(Subtopic.id == subtopic_id))
        subtopic = result.scalar_one_or_none()
        if subtopic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtopic not found")
        return subtopic


    async def ensure_topic_name_is_unique(
        session: "AsyncSession",
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(Topic).where(Topic.name == name))
        topic = result.scalar_one_or_none()
        if topic is not None and topic.id != current_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Topic name must be unique")


    async def ensure_subtopic_name_is_unique(
        session: "AsyncSession",
        topic_id: uuid.UUID,
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(
            select(Subtopic).where(Subtopic.topic_id == topic_id, Subtopic.name == name)
        )
        subtopic = result.scalar_one_or_none()
        if subtopic is not None and subtopic.id != current_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subtopic name must be unique inside the topic",
            )


    @router.get("/topics", response_model=list[TopicResponse], status_code=200)
    async def list_topics() -> list[TopicResponse]:
        async with db.session_ctx() as session:
            result = await session.execute(select(Topic).order_by(Topic.name))
            topics = result.scalars().all()
            return [TopicResponse.model_validate(item) for item in topics]


    @router.get("/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def get_topic(topic_id: uuid.UUID) -> TopicResponse:
        async with db.session_ctx() as session:
            topic = await get_topic_or_404(session, topic_id)
            return TopicResponse.model_validate(topic)


    @router.get("/subtopics", response_model=list[SubtopicResponse], status_code=200)
    async def list_subtopics(
        topic_id: str | None = Query(default=None),
    ) -> list[SubtopicResponse]:
        parsed_topic_id = parse_optional_uuid(topic_id, "topic_id")
        async with db.session_ctx() as session:
            statement = select(Subtopic).order_by(Subtopic.name)
            if parsed_topic_id is not None:
                statement = statement.where(Subtopic.topic_id == parsed_topic_id)
            result = await session.execute(statement)
            subtopics = result.scalars().all()
            return [SubtopicResponse.model_validate(item) for item in subtopics]


    @router.get("/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def get_subtopic(subtopic_id: uuid.UUID) -> SubtopicResponse:
        async with db.session_ctx() as session:
            subtopic = await get_subtopic_or_404(session, subtopic_id)
            return SubtopicResponse.model_validate(subtopic)


    @router.post("/admin/topics", response_model=TopicResponse, status_code=201)
    async def create_topic(
        data: TopicCreate,
        _: "User" = Depends(current_admin),
    ) -> TopicResponse:
        async with db.session_ctx() as session:
            await ensure_topic_name_is_unique(session, data.name)
            topic = Topic(name=data.name)
            session.add(topic)
            await session.flush()
            await session.refresh(topic)
        await mastery_cache_manager.bump_taxonomy_version()
        async with db.session_ctx() as session:
            topic = await get_topic_or_404(session, topic.id)
            return TopicResponse.model_validate(topic)


    @router.get("/admin/topics", response_model=list[TopicResponse], status_code=200)
    async def list_admin_topics(_: "User" = Depends(current_admin)) -> list[TopicResponse]:
        return await list_topics()


    @router.get("/admin/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def get_admin_topic(
        topic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> TopicResponse:
        return await get_topic(topic_id)


    @router.patch("/admin/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def update_topic(
        topic_id: uuid.UUID,
        data: TopicUpdate,
        _: "User" = Depends(current_admin),
    ) -> TopicResponse:
        async with db.session_ctx() as session:
            topic = await get_topic_or_404(session, topic_id)
            if data.name is not None:
                await ensure_topic_name_is_unique(session, data.name, current_id=topic.id)
                topic.name = data.name
            await session.flush()
            await session.refresh(topic)
        return TopicResponse.model_validate(topic)


    @router.delete("/admin/topics/{topic_id}", response_model=MessageResponse, status_code=200)
    async def delete_topic(
        topic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> MessageResponse:
        async with db.session_ctx() as session:
            topic = await get_topic_or_404(session, topic_id)
            await session.delete(topic)
        await mastery_cache_manager.bump_taxonomy_version()
        return MessageResponse(message="Topic deleted")


    @router.post("/admin/subtopics", response_model=SubtopicResponse, status_code=201)
    async def create_subtopic(
        data: SubtopicCreate,
        _: "User" = Depends(current_admin),
    ) -> SubtopicResponse:
        async with db.session_ctx() as session:
            await get_topic_or_404(session, data.topic_id)
            await ensure_subtopic_name_is_unique(session, data.topic_id, data.name)
            subtopic = Subtopic(topic_id=data.topic_id, name=data.name)
            session.add(subtopic)
            await session.flush()
            session.add(TopicSubtopic(topic_id=data.topic_id, subtopic_id=subtopic.id, weight=1.0))
            await session.refresh(subtopic)
        await mastery_cache_manager.bump_taxonomy_version()
        async with db.session_ctx() as session:
            subtopic = await get_subtopic_or_404(session, subtopic.id)
            return SubtopicResponse.model_validate(subtopic)


    @router.get("/admin/subtopics", response_model=list[SubtopicResponse], status_code=200)
    async def list_admin_subtopics(
        topic_id: str | None = Query(default=None),
        _: "User" = Depends(current_admin),
    ) -> list[SubtopicResponse]:
        return await list_subtopics(topic_id)


    @router.get("/admin/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def get_admin_subtopic(
        subtopic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> SubtopicResponse:
        return await get_subtopic(subtopic_id)


    @router.patch("/admin/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def update_subtopic(
        subtopic_id: uuid.UUID,
        data: SubtopicUpdate,
        _: "User" = Depends(current_admin),
    ) -> SubtopicResponse:
        async with db.session_ctx() as session:
            subtopic = await get_subtopic_or_404(session, subtopic_id)
            taxonomy_mapping_changed = False

            if data.topic_id is not None:
                await get_topic_or_404(session, data.topic_id)
                subtopic.topic_id = data.topic_id
                taxonomy_mapping_changed = True
                if data.name is None:
                    await ensure_subtopic_name_is_unique(
                        session,
                        data.topic_id,
                        subtopic.name,
                        current_id=subtopic.id,
                    )

            if data.name is not None:
                await ensure_subtopic_name_is_unique(
                    session,
                    data.topic_id or subtopic.topic_id,
                    data.name,
                    current_id=subtopic.id,
                )
                subtopic.name = data.name

            if taxonomy_mapping_changed:
                await session.execute(
                    delete(TopicSubtopic).where(TopicSubtopic.subtopic_id == subtopic.id)
                )
                session.add(TopicSubtopic(topic_id=subtopic.topic_id, subtopic_id=subtopic.id, weight=1.0))

            await session.flush()
            await session.refresh(subtopic)
        if taxonomy_mapping_changed:
            await mastery_cache_manager.bump_taxonomy_version()
        return SubtopicResponse.model_validate(subtopic)


    @router.delete("/admin/subtopics/{subtopic_id}", response_model=MessageResponse, status_code=200)
    async def delete_subtopic(
        subtopic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> MessageResponse:
        async with db.session_ctx() as session:
            subtopic = await get_subtopic_or_404(session, subtopic_id)
            await session.delete(subtopic)
        await mastery_cache_manager.bump_taxonomy_version()
        return MessageResponse(message="Subtopic deleted")


    return router
