from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from src.fast_api.dependencies import (
    build_current_admin_dependency,
    build_current_user_dependency,
    parse_optional_uuid,
)
from src.pydantic_schemas import (
    AdminProblemResponse,
    MessageResponse,
    ProblemCreate,
    ProblemResponse,
    ProblemSubmitRequest,
    ProblemSubmitResponse,
    ProblemUpdate,
    StudentProgressResponse,
)
from src.services.problem_service import ProblemService

if TYPE_CHECKING:
    from src.db.database import DataBase
    from src.db.models import User


def get_problem_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    current_admin = build_current_admin_dependency(db)
    current_user = build_current_user_dependency(db)
    problem_service = ProblemService(db)


    @router.get("/problems", response_model=list[ProblemResponse], status_code=200)
    async def list_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        subskill_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[ProblemResponse]:
        response = await problem_service.list_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            subskill_id=parse_optional_uuid(subskill_id, "subskill_id"),
            limit=limit,
            offset=offset,
            include_admin_data=False,
        )
        return [item for item in response if isinstance(item, ProblemResponse)]


    @router.get("/problems/{problem_id}", response_model=ProblemResponse, status_code=200)
    async def get_problem(problem_id: uuid.UUID) -> ProblemResponse:
        response = await problem_service.get_problem(problem_id, include_admin_data=False)
        if not isinstance(response, ProblemResponse):
            raise RuntimeError("Expected public problem response")
        return response


    @router.get("/student/progress", response_model=StudentProgressResponse, status_code=200)
    async def get_student_progress(user: "User" = Depends(current_user)) -> StudentProgressResponse:
        return await problem_service.get_student_progress(user.id)


    @router.post(
        "/student/problems/{problem_id}/submit",
        response_model=ProblemSubmitResponse,
        status_code=200,
    )
    async def submit_problem(
        problem_id: uuid.UUID,
        data: ProblemSubmitRequest,
        user: "User" = Depends(current_user),
    ) -> ProblemSubmitResponse:
        return await problem_service.submit_problem(user.id, problem_id, data.answer_option_id)


    @router.post("/admin/problems", response_model=AdminProblemResponse, status_code=201)
    async def create_problem(
        data: ProblemCreate,
        _: "User" = Depends(current_admin),
    ) -> AdminProblemResponse:
        return await problem_service.create_problem(data)


    @router.get("/admin/problems", response_model=list[AdminProblemResponse], status_code=200)
    async def list_admin_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        subskill_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        _: "User" = Depends(current_admin),
    ) -> list[AdminProblemResponse]:
        response = await problem_service.list_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            subskill_id=parse_optional_uuid(subskill_id, "subskill_id"),
            limit=limit,
            offset=offset,
            include_admin_data=True,
        )
        return [item for item in response if isinstance(item, AdminProblemResponse)]


    @router.get("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def get_admin_problem(
        problem_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> AdminProblemResponse:
        response = await problem_service.get_problem(problem_id, include_admin_data=True)
        if not isinstance(response, AdminProblemResponse):
            raise RuntimeError("Expected admin problem response")
        return response


    @router.patch("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def update_problem(
        problem_id: uuid.UUID,
        data: ProblemUpdate,
        _: "User" = Depends(current_admin),
    ) -> AdminProblemResponse:
        return await problem_service.update_problem(problem_id, data)


    @router.delete("/admin/problems/{problem_id}", response_model=MessageResponse, status_code=200)
    async def delete_problem(
        problem_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> MessageResponse:
        await problem_service.delete_problem(problem_id)
        return MessageResponse(message="Problem deleted")


    return router
