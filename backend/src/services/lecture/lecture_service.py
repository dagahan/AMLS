from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.logging import get_logger
from src.models.alchemy import CourseNode, Lecture, LecturePage
from src.models.pydantic.lecture import (
    LectureCreate,
    LectureDetailResponse,
    LecturePageCreate,
    LecturePageResponse,
    LectureResponse,
)
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class LectureService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def create_lecture(
        self,
        course_node_id: uuid.UUID,
        data: LectureCreate,
    ) -> LectureResponse:
        async with self.storage_manager.session_ctx() as session:
            course_node = await session.get(CourseNode, course_node_id)
            if course_node is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course node not found",
                )

            lecture = Lecture(course_node_id=course_node_id, title=data.title)
            session.add(lecture)
            await session.flush()
            logger.info(
                "Created lecture: lecture_id={}, course_node_id={}, title={}",
                lecture.id,
                course_node_id,
                data.title,
            )
            return LectureResponse.model_validate(lecture)


    async def list_course_node_lectures(self, course_node_id: uuid.UUID) -> list[LectureResponse]:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(
                select(Lecture)
                .where(Lecture.course_node_id == course_node_id)
                .order_by(Lecture.created_at, Lecture.id)
            )
            lectures = result.scalars().all()
            return [LectureResponse.model_validate(lecture) for lecture in lectures]


    async def add_lecture_page(
        self,
        lecture_id: uuid.UUID,
        data: LecturePageCreate,
    ) -> LecturePageResponse:
        async with self.storage_manager.session_ctx() as session:
            lecture = await self._load_lecture_or_404(session, lecture_id)
            existing_page_numbers = [page.page_number for page in lecture.pages]
            expected_page_number = len(existing_page_numbers) + 1
            if data.page_number != expected_page_number:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Lecture page number must be {expected_page_number}",
                )

            lecture_page = LecturePage(
                lecture_id=lecture_id,
                page_number=data.page_number,
                page_content=data.page_content,
            )
            session.add(lecture_page)
            await session.flush()
            logger.info(
                "Added lecture page: lecture_page_id={}, lecture_id={}, page_number={}",
                lecture_page.id,
                lecture_id,
                data.page_number,
            )
            return LecturePageResponse.model_validate(lecture_page)


    async def get_lecture(self, lecture_id: uuid.UUID) -> LectureDetailResponse:
        async with self.storage_manager.session_ctx() as session:
            lecture = await self._load_lecture_or_404(session, lecture_id)
            pages = sorted(lecture.pages, key=lambda page: (page.page_number, str(page.id)))
            return LectureDetailResponse(
                lecture=LectureResponse.model_validate(lecture),
                pages=[LecturePageResponse.model_validate(page) for page in pages],
            )


    async def _load_lecture_or_404(
        self,
        session: AsyncSession,
        lecture_id: uuid.UUID,
    ) -> Lecture:
        result = await session.execute(
            select(Lecture)
            .options(selectinload(Lecture.pages))
            .where(Lecture.id == lecture_id)
        )
        lecture = result.scalar_one_or_none()
        if lecture is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        return lecture
