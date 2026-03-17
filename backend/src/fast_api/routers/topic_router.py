from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from src.db.models import Subtopic, Topic
from src.fast_api.dependencies import build_current_admin_dependency
from src.pydantic_schemas import (
    MessageResponse,
    SubtopicCreate,
    SubtopicResponse,
    SubtopicUpdate,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.db.models import User


def get_topic_router(db: "DataBase") -> APIRouter:
    router = APIRouter(tags=["admin-topics"])
    current_admin = build_current_admin_dependency(db)


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


    @router.post("/admin/topics", response_model=TopicResponse, status_code=201)
    async def create_topic(
        data: TopicCreate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> TopicResponse:
        await ensure_topic_name_is_unique(session, data.name)
        topic = Topic(name=data.name)
        session.add(topic)
        await session.commit()
        await session.refresh(topic)
        return TopicResponse.model_validate(topic)


    @router.get("/admin/topics", response_model=list[TopicResponse], status_code=200)
    async def list_topics(
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> list[TopicResponse]:
        result = await session.execute(select(Topic).order_by(Topic.name))
        topics = result.scalars().all()
        return [TopicResponse.model_validate(item) for item in topics]


    @router.get("/admin/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def get_topic(
        topic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> TopicResponse:
        topic = await get_topic_or_404(session, topic_id)
        return TopicResponse.model_validate(topic)


    @router.patch("/admin/topics/{topic_id}", response_model=TopicResponse, status_code=200)
    async def update_topic(
        topic_id: uuid.UUID,
        data: TopicUpdate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> TopicResponse:
        topic = await get_topic_or_404(session, topic_id)
        if data.name is not None:
            await ensure_topic_name_is_unique(session, data.name, current_id=topic.id)
            topic.name = data.name
        await session.commit()
        await session.refresh(topic)
        return TopicResponse.model_validate(topic)


    @router.delete("/admin/topics/{topic_id}", response_model=MessageResponse, status_code=200)
    async def delete_topic(
        topic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> MessageResponse:
        topic = await get_topic_or_404(session, topic_id)
        await session.delete(topic)
        await session.commit()
        return MessageResponse(message="Topic deleted")


    @router.post("/admin/subtopics", response_model=SubtopicResponse, status_code=201)
    async def create_subtopic(
        data: SubtopicCreate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> SubtopicResponse:
        await get_topic_or_404(session, data.topic_id)
        await ensure_subtopic_name_is_unique(session, data.topic_id, data.name)
        subtopic = Subtopic(topic_id=data.topic_id, name=data.name)
        session.add(subtopic)
        await session.commit()
        await session.refresh(subtopic)
        return SubtopicResponse.model_validate(subtopic)


    @router.get("/admin/subtopics", response_model=list[SubtopicResponse], status_code=200)
    async def list_subtopics(
        topic_id: uuid.UUID | None = Query(default=None),
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> list[SubtopicResponse]:
        statement = select(Subtopic).order_by(Subtopic.name)
        if topic_id is not None:
            statement = statement.where(Subtopic.topic_id == topic_id)
        result = await session.execute(statement)
        subtopics = result.scalars().all()
        return [SubtopicResponse.model_validate(item) for item in subtopics]


    @router.get("/admin/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def get_subtopic(
        subtopic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> SubtopicResponse:
        subtopic = await get_subtopic_or_404(session, subtopic_id)
        return SubtopicResponse.model_validate(subtopic)


    @router.patch("/admin/subtopics/{subtopic_id}", response_model=SubtopicResponse, status_code=200)
    async def update_subtopic(
        subtopic_id: uuid.UUID,
        data: SubtopicUpdate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> SubtopicResponse:
        subtopic = await get_subtopic_or_404(session, subtopic_id)

        if data.topic_id is not None:
            await get_topic_or_404(session, data.topic_id)
            subtopic.topic_id = data.topic_id
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

        await session.commit()
        await session.refresh(subtopic)
        return SubtopicResponse.model_validate(subtopic)


    @router.delete("/admin/subtopics/{subtopic_id}", response_model=MessageResponse, status_code=200)
    async def delete_subtopic(
        subtopic_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> MessageResponse:
        subtopic = await get_subtopic_or_404(session, subtopic_id)
        await session.delete(subtopic)
        await session.commit()
        return MessageResponse(message="Subtopic deleted")


    return router
