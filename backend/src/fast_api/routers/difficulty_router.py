from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from src.db.enums import UserRole
from src.fast_api.dependencies import require_role
from src.models.pydantic import (
    AuthContext,
    DifficultyCreate,
    DifficultyResponse,
    DifficultyUpdate,
    MessageResponse,
)
from src.services.catalog import DifficultyService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_difficulty_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    difficulty_service = DifficultyService(db)


    @router.get("/difficulties", response_model=list[DifficultyResponse], status_code=200)
    async def list_difficulties(
        auth: AuthContext = Depends(require_role()),
    ) -> list[DifficultyResponse]:
        return await difficulty_service.list_difficulties()


    @router.get("/difficulties/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def get_difficulty(
        difficulty_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> DifficultyResponse:
        return await difficulty_service.get_difficulty(difficulty_id)


    @router.post("/admin/difficulties", response_model=DifficultyResponse, status_code=201)
    async def create_difficulty(
        data: DifficultyCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> DifficultyResponse:
        return await difficulty_service.create_difficulty(data)


    @router.get("/admin/difficulties", response_model=list[DifficultyResponse], status_code=200)
    async def list_admin_difficulties(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[DifficultyResponse]:
        return await difficulty_service.list_difficulties()


    @router.get("/admin/difficulties/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def get_admin_difficulty(
        difficulty_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> DifficultyResponse:
        return await difficulty_service.get_difficulty(difficulty_id)


    @router.patch("/admin/difficulties/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def update_difficulty(
        difficulty_id: uuid.UUID,
        data: DifficultyUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> DifficultyResponse:
        return await difficulty_service.update_difficulty(difficulty_id, data)


    @router.delete("/admin/difficulties/{difficulty_id}", response_model=MessageResponse, status_code=200)
    async def delete_difficulty(
        difficulty_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        await difficulty_service.delete_difficulty(difficulty_id)
        return MessageResponse(message="Difficulty deleted")


    return router
