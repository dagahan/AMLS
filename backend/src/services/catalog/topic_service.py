from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from src.models.alchemy import Subtopic, Topic, TopicSubtopic
from src.models.pydantic import (
    SubtopicCreate,
    SubtopicResponse,
    SubtopicUpdate,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TopicService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def list_topics(self) -> list[TopicResponse]:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(select(Topic).order_by(Topic.name))
            topics = result.scalars().all()
        return [TopicResponse.model_validate(item) for item in topics]


    async def get_topic(self, topic_id: uuid.UUID) -> TopicResponse:
        async with self.storage_manager.session_ctx() as session:
            topic = await self._get_topic_or_404(session, topic_id)
            return TopicResponse.model_validate(topic)


    async def list_subtopics(self, topic_id: uuid.UUID | None = None) -> list[SubtopicResponse]:
        async with self.storage_manager.session_ctx() as session:
            statement = select(Subtopic).order_by(Subtopic.name)
            if topic_id is not None:
                statement = statement.where(Subtopic.topic_id == topic_id)
            result = await session.execute(statement)
            subtopics = result.scalars().all()
        return [SubtopicResponse.model_validate(item) for item in subtopics]


    async def get_subtopic(self, subtopic_id: uuid.UUID) -> SubtopicResponse:
        async with self.storage_manager.session_ctx() as session:
            subtopic = await self._get_subtopic_or_404(session, subtopic_id)
            return SubtopicResponse.model_validate(subtopic)


    async def create_topic(self, data: TopicCreate) -> TopicResponse:
        async with self.storage_manager.session_ctx() as session:
            await self._ensure_topic_name_is_unique(session, data.name)
            topic = Topic(name=data.name)
            session.add(topic)
            await session.flush()
            await session.refresh(topic)
            return TopicResponse.model_validate(topic)


    async def update_topic(self, topic_id: uuid.UUID, data: TopicUpdate) -> TopicResponse:
        async with self.storage_manager.session_ctx() as session:
            topic = await self._get_topic_or_404(session, topic_id)
            if data.name is not None:
                await self._ensure_topic_name_is_unique(session, data.name, current_id=topic.id)
                topic.name = data.name
            await session.flush()
            await session.refresh(topic)
            return TopicResponse.model_validate(topic)


    async def delete_topic(self, topic_id: uuid.UUID) -> None:
        async with self.storage_manager.session_ctx() as session:
            topic = await self._get_topic_or_404(session, topic_id)
            await session.delete(topic)


    async def create_subtopic(self, data: SubtopicCreate) -> SubtopicResponse:
        async with self.storage_manager.session_ctx() as session:
            await self._get_topic_or_404(session, data.topic_id)
            await self._ensure_subtopic_name_is_unique(session, data.topic_id, data.name)
            subtopic = Subtopic(topic_id=data.topic_id, name=data.name)
            session.add(subtopic)
            await session.flush()
            session.add(TopicSubtopic(topic_id=data.topic_id, subtopic_id=subtopic.id, weight=1.0))
            await session.refresh(subtopic)
            return SubtopicResponse.model_validate(subtopic)


    async def update_subtopic(
        self,
        subtopic_id: uuid.UUID,
        data: SubtopicUpdate,
    ) -> SubtopicResponse:
        async with self.storage_manager.session_ctx() as session:
            subtopic = await self._get_subtopic_or_404(session, subtopic_id)
            taxonomy_mapping_changed = False

            if data.topic_id is not None:
                await self._get_topic_or_404(session, data.topic_id)
                subtopic.topic_id = data.topic_id
                taxonomy_mapping_changed = True
                if data.name is None:
                    await self._ensure_subtopic_name_is_unique(
                        session,
                        data.topic_id,
                        subtopic.name,
                        current_id=subtopic.id,
                    )

            if data.name is not None:
                await self._ensure_subtopic_name_is_unique(
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
            return SubtopicResponse.model_validate(subtopic)


    async def delete_subtopic(self, subtopic_id: uuid.UUID) -> None:
        async with self.storage_manager.session_ctx() as session:
            subtopic = await self._get_subtopic_or_404(session, subtopic_id)
            await session.delete(subtopic)


    async def _get_topic_or_404(self, session: AsyncSession, topic_id: uuid.UUID) -> Topic:
        result = await session.execute(select(Topic).where(Topic.id == topic_id))
        topic = result.scalar_one_or_none()
        if topic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
        return topic


    async def _get_subtopic_or_404(self, session: AsyncSession, subtopic_id: uuid.UUID) -> Subtopic:
        result = await session.execute(select(Subtopic).where(Subtopic.id == subtopic_id))
        subtopic = result.scalar_one_or_none()
        if subtopic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtopic not found")
        return subtopic


    async def _ensure_topic_name_is_unique(
        self,
        session: AsyncSession,
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(Topic).where(Topic.name == name))
        topic = result.scalar_one_or_none()
        if topic is not None and topic.id != current_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Topic name must be unique")


    async def _ensure_subtopic_name_is_unique(
        self,
        session: AsyncSession,
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
