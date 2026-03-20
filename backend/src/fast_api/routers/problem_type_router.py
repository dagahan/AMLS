from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from src.db.enums import UserRole
from src.fast_api.dependencies import require_role
from src.models.pydantic import (
    AuthContext,
    MessageResponse,
    ProblemTypeCreate,
    ProblemTypeGraphResponse,
    ProblemTypeResponse,
    ProblemTypeUpdate,
)
from src.services.catalog import ProblemTypeService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_problem_type_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    problem_type_service = ProblemTypeService(db)


    @router.get("/problem-types", response_model=list[ProblemTypeResponse], status_code=200)
    async def list_problem_types(
        auth: AuthContext = Depends(require_role()),
    ) -> list[ProblemTypeResponse]:
        return await problem_type_service.list_problem_types()


    @router.get("/problem-types/graph", response_model=ProblemTypeGraphResponse, status_code=200)
    async def get_problem_type_graph(
        auth: AuthContext = Depends(require_role()),
    ) -> ProblemTypeGraphResponse:
        return await problem_type_service.get_problem_type_graph()


    @router.get("/problem-types/{problem_type_id}", response_model=ProblemTypeResponse, status_code=200)
    async def get_problem_type(
        problem_type_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> ProblemTypeResponse:
        return await problem_type_service.get_problem_type(problem_type_id)


    @router.post("/admin/problem-types", response_model=ProblemTypeResponse, status_code=201)
    async def create_problem_type(
        data: ProblemTypeCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> ProblemTypeResponse:
        return await problem_type_service.create_problem_type(data)


    @router.get("/admin/problem-types", response_model=list[ProblemTypeResponse], status_code=200)
    async def list_admin_problem_types(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[ProblemTypeResponse]:
        return await problem_type_service.list_problem_types()


    @router.get("/admin/problem-types/graph", response_model=ProblemTypeGraphResponse, status_code=200)
    async def get_admin_problem_type_graph(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> ProblemTypeGraphResponse:
        return await problem_type_service.get_problem_type_graph()


    @router.get("/admin/problem-types/{problem_type_id}", response_model=ProblemTypeResponse, status_code=200)
    async def get_admin_problem_type(
        problem_type_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> ProblemTypeResponse:
        return await problem_type_service.get_problem_type(problem_type_id)


    @router.patch("/admin/problem-types/{problem_type_id}", response_model=ProblemTypeResponse, status_code=200)
    async def update_problem_type(
        problem_type_id: uuid.UUID,
        data: ProblemTypeUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> ProblemTypeResponse:
        return await problem_type_service.update_problem_type(problem_type_id, data)


    @router.delete("/admin/problem-types/{problem_type_id}", response_model=MessageResponse, status_code=200)
    async def delete_problem_type(
        problem_type_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        await problem_type_service.delete_problem_type(problem_type_id)
        return MessageResponse(message="Problem type deleted")


    return router
