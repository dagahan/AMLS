from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext, MessageResponse
from src.models.pydantic.course import CourseCreate, CourseEnrollmentResponse, CourseResponse
from src.services.course import CourseService
from src.services.test import TestService
from src.storage.db.enums import UserRole
from src.storage.storage_manager import StorageManager


def get_course_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["courses"])
    course_service = CourseService(storage_manager)
    test_service = TestService(storage_manager)


    @router.get("/courses", response_model=list[CourseResponse], status_code=200)
    async def list_courses(
        auth: AuthContext = Depends(require_role()),
    ) -> list[CourseResponse]:
        return await course_service.list_courses()


    @router.get("/courses/active", response_model=list[CourseResponse], status_code=200)
    async def list_active_courses(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> list[CourseResponse]:
        return await course_service.list_active_courses(auth.user.id)


    @router.post("/admin/courses", response_model=CourseResponse, status_code=201)
    async def create_course(
        data: CourseCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseResponse:
        return await course_service.create_course(auth.user.id, data)


    @router.post(
        "/courses/{course_id}/enroll",
        response_model=CourseEnrollmentResponse,
        status_code=201,
    )
    async def enroll_into_course(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> CourseEnrollmentResponse:
        return await course_service.enroll_user(auth.user.id, course_id)


    @router.post("/courses/{course_id}/reset", response_model=MessageResponse, status_code=200)
    async def reset_course(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> MessageResponse:
        await test_service.reset_course(auth.user.id, course_id)
        return MessageResponse(message="Course reset")


    return router
