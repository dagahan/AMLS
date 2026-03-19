from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from src.fast_api.dependencies import (
    ensure_admin_user,
    get_current_user,
    parse_optional_uuid,
)
from src.models.pydantic import (
    AdminProblemResponse,
    MessageResponse,
    ProblemCreate,
    ProblemResponse,
    ProblemSubmitRequest,
    ProblemSubmitResponse,
    ProblemUpdate,
    StudentProgressResponse,
)
from src.services.problem.admin_problem_service import AdminProblemService
from src.services.problem.problem_query_service import ProblemQueryService
from src.services.problem.problem_submission_service import ProblemSubmissionService

if TYPE_CHECKING:
    from src.db.database import DataBase
    from src.models.alchemy import User


def get_problem_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    admin_problem_service = AdminProblemService(db)
    problem_query_service = ProblemQueryService(db)
    problem_submission_service = ProblemSubmissionService(db)


    @router.get("/problems", response_model=list[ProblemResponse], status_code=200)
    async def list_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        skill_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[ProblemResponse]:
        return await problem_query_service.list_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            skill_id=parse_optional_uuid(skill_id, "skill_id"),
            limit=limit,
            offset=offset,
        )


    @router.get("/problems/{problem_id}", response_model=ProblemResponse, status_code=200)
    async def get_problem(problem_id: uuid.UUID) -> ProblemResponse:
        return await problem_query_service.get_problem(problem_id)


    @router.get("/student/progress", response_model=StudentProgressResponse, status_code=200)
    async def get_student_progress(user: "User" = Depends(get_current_user)) -> StudentProgressResponse:
        return await problem_submission_service.get_student_progress(user.id)


    @router.post(
        "/student/problems/{problem_id}/submit",
        response_model=ProblemSubmitResponse,
        status_code=200,
    )
    async def submit_problem(
        problem_id: uuid.UUID,
        data: ProblemSubmitRequest,
        user: "User" = Depends(get_current_user),
    ) -> ProblemSubmitResponse:
        return await problem_submission_service.submit_problem(user.id, problem_id, data.answer_option_id)


    @router.post("/admin/problems", response_model=AdminProblemResponse, status_code=201)
    async def create_problem(
        data: ProblemCreate,
        user: "User" = Depends(get_current_user),
    ) -> AdminProblemResponse:
        ensure_admin_user(user)
        return await admin_problem_service.create_problem(data)


    @router.get("/admin/problems", response_model=list[AdminProblemResponse], status_code=200)
    async def list_admin_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        skill_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        user: "User" = Depends(get_current_user),
    ) -> list[AdminProblemResponse]:
        ensure_admin_user(user)
        return await problem_query_service.list_admin_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            skill_id=parse_optional_uuid(skill_id, "skill_id"),
            limit=limit,
            offset=offset,
        )


    @router.get("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def get_admin_problem(
        problem_id: uuid.UUID,
        user: "User" = Depends(get_current_user),
    ) -> AdminProblemResponse:
        ensure_admin_user(user)
        return await problem_query_service.get_admin_problem(problem_id)


    @router.patch("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def update_problem(
        problem_id: uuid.UUID,
        data: ProblemUpdate,
        user: "User" = Depends(get_current_user),
    ) -> AdminProblemResponse:
        ensure_admin_user(user)
        return await admin_problem_service.update_problem(problem_id, data)


    @router.delete("/admin/problems/{problem_id}", response_model=MessageResponse, status_code=200)
    async def delete_problem(
        problem_id: uuid.UUID,
        user: "User" = Depends(get_current_user),
    ) -> MessageResponse:
        ensure_admin_user(user)
        await admin_problem_service.delete_problem(problem_id)
        return MessageResponse(message="Problem deleted")


    return router
