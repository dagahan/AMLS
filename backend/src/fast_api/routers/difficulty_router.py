from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from src.db.enums import DifficultyLevel
from src.fast_api.dependencies import require_role
from src.models.pydantic import (
    AuthContext,
    DifficultyResponse,
)
from src.services.catalog import DifficultyService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_difficulty_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    difficulty_service = DifficultyService()


    @router.get("/difficulties", response_model=list[DifficultyResponse], status_code=200)
    async def list_difficulties(
        auth: AuthContext = Depends(require_role()),
    ) -> list[DifficultyResponse]:
        return await difficulty_service.list_difficulties()


    @router.get("/difficulties/{difficulty_key}", response_model=DifficultyResponse, status_code=200)
    async def get_difficulty(
        difficulty_key: DifficultyLevel,
        auth: AuthContext = Depends(require_role()),
    ) -> DifficultyResponse:
        return await difficulty_service.get_difficulty(difficulty_key)


    return router
