from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select

from src.core.logging import get_logger
from src.models.alchemy import Course, CourseEnrollment
from src.models.pydantic.course import CourseEnrollmentResponse, CourseCreate, CourseResponse
from src.storage.storage_manager import StorageManager


logger = get_logger(__name__)


class CourseService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def create_course(self, author_id: uuid.UUID, data: CourseCreate) -> CourseResponse:
        async with self.storage_manager.session_ctx() as session:
            course = Course(
                author_id=author_id,
                title=data.title,
                description=data.description,
            )
            session.add(course)
            await session.flush()
            logger.info(
                "Created course: course_id={}, author_id={}, title={}",
                course.id,
                author_id,
                data.title,
            )
            return CourseResponse.model_validate(course)


    async def list_courses(self) -> list[CourseResponse]:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(select(Course).order_by(Course.created_at.desc()))
            courses = result.scalars().all()
            return [CourseResponse.model_validate(course) for course in courses]


    async def list_active_courses(self, user_id: uuid.UUID) -> list[CourseResponse]:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(
                select(Course)
                .join(CourseEnrollment, CourseEnrollment.course_id == Course.id)
                .where(
                    CourseEnrollment.user_id == user_id,
                    CourseEnrollment.is_active.is_(True),
                )
                .order_by(Course.created_at.desc())
            )
            courses = result.scalars().all()
            return [CourseResponse.model_validate(course) for course in courses]


    async def enroll_user(self, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseEnrollmentResponse:
        async with self.storage_manager.session_ctx() as session:
            course = await session.get(Course, course_id)
            if course is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )

            result = await session.execute(
                select(CourseEnrollment).where(
                    CourseEnrollment.user_id == user_id,
                    CourseEnrollment.course_id == course_id,
                )
            )
            course_enrollment = result.scalar_one_or_none()
            if course_enrollment is None:
                course_enrollment = CourseEnrollment(
                    user_id=user_id,
                    course_id=course_id,
                    is_active=True,
                )
                session.add(course_enrollment)
                await session.flush()
                logger.info(
                    "Created course enrollment: enrollment_id={}, user_id={}, course_id={}",
                    course_enrollment.id,
                    user_id,
                    course_id,
                )
            elif not course_enrollment.is_active:
                course_enrollment.is_active = True
                await session.flush()
                logger.info(
                    "Reactivated course enrollment: enrollment_id={}, user_id={}, course_id={}",
                    course_enrollment.id,
                    user_id,
                    course_id,
                )

            return CourseEnrollmentResponse.model_validate(course_enrollment)
