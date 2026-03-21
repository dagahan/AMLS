from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from src.db.enums import UserRole
from src.fast_api.dependencies import parse_optional_uuid, require_role
from src.models.pydantic import (
    AdminProblemResponse,
    AuthContext,
    MessageResponse,
    ProblemCreate,
    ProblemResponse,
    ProblemUpdate,
)
from src.services.problem.admin_problem_service import AdminProblemService
from src.services.problem.problem_query_service import ProblemQueryService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_problem_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    admin_problem_service = AdminProblemService(db)
    problem_query_service = ProblemQueryService(db)


    @router.get("/problems", response_model=list[ProblemResponse], status_code=200)
    async def list_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        problem_type_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        auth: AuthContext = Depends(require_role()),
    ) -> list[ProblemResponse]:
        return await problem_query_service.list_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            problem_type_id=parse_optional_uuid(problem_type_id, "problem_type_id"),
            limit=limit,
            offset=offset,
        )


    @router.get("/problems/{problem_id}", response_model=ProblemResponse, status_code=200)
    async def get_problem(
        problem_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> ProblemResponse:
        return await problem_query_service.get_problem(problem_id)


    @router.post("/admin/problems", response_model=AdminProblemResponse, status_code=201)
    async def create_problem(
        data: ProblemCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> AdminProblemResponse:
        return await admin_problem_service.create_problem(data)


    @router.get("/admin/problems", response_model=list[AdminProblemResponse], status_code=200)
    async def list_admin_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        problem_type_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[AdminProblemResponse]:
        return await problem_query_service.list_admin_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            problem_type_id=parse_optional_uuid(problem_type_id, "problem_type_id"),
            limit=limit,
            offset=offset,
        )


    @router.get("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def get_admin_problem(
        problem_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> AdminProblemResponse:
        return await problem_query_service.get_admin_problem(problem_id)


    @router.patch("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def update_problem(
        problem_id: uuid.UUID,
        data: ProblemUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> AdminProblemResponse:
        return await admin_problem_service.update_problem(problem_id, data)


    @router.delete("/admin/problems/{problem_id}", response_model=MessageResponse, status_code=200)
    async def delete_problem(
        problem_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        await admin_problem_service.delete_problem(problem_id)
        return MessageResponse(message="Problem deleted")


    return router
