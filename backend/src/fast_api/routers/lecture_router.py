from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext
from src.models.pydantic.lecture import (
    LectureCreate,
    LectureDetailResponse,
    LecturePageCreate,
    LecturePageResponse,
    LectureResponse,
)
from src.services.lecture import LectureService
from src.storage.db.enums import UserRole
from src.storage.storage_manager import StorageManager


def get_lecture_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["lectures"])
    lecture_service = LectureService(storage_manager)


    @router.post(
        "/admin/course-nodes/{course_node_id}/lectures",
        response_model=LectureResponse,
        status_code=201,
    )
    async def create_lecture(
        course_node_id: uuid.UUID,
        data: LectureCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> LectureResponse:
        return await lecture_service.create_lecture(course_node_id, data)


    @router.get(
        "/course-nodes/{course_node_id}/lectures",
        response_model=list[LectureResponse],
        status_code=200,
    )
    async def list_course_node_lectures(
        course_node_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> list[LectureResponse]:
        return await lecture_service.list_course_node_lectures(course_node_id)


    @router.get("/lectures/{lecture_id}", response_model=LectureDetailResponse, status_code=200)
    async def get_lecture(
        lecture_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> LectureDetailResponse:
        return await lecture_service.get_lecture(lecture_id)


    @router.post(
        "/admin/lectures/{lecture_id}/pages",
        response_model=LecturePageResponse,
        status_code=201,
    )
    async def add_lecture_page(
        lecture_id: uuid.UUID,
        data: LecturePageCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> LecturePageResponse:
        return await lecture_service.add_lecture_page(lecture_id, data)


    return router
