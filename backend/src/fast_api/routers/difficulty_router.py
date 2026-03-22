from __future__ import annotations

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext, DifficultyResponse
from src.services.catalog import DifficultyService
from src.storage.storage_manager import StorageManager
from src.storage.db.enums import DifficultyLevel


def get_difficulty_router(_storage_manager: StorageManager) -> APIRouter:
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
