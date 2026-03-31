from __future__ import annotations

from fastapi import HTTPException, status

from src.config import get_app_config
from src.storage.db.enums import DifficultyLevel
from src.models.pydantic import DifficultyResponse


def build_difficulty_response(difficulty_level: DifficultyLevel) -> DifficultyResponse:
    config = get_app_config().difficulty(difficulty_level.value)
    return DifficultyResponse(
        key=difficulty_level,
        name=config.name,
        coefficient=config.coefficient,
    )


class DifficultyService:
    async def list_difficulties(self) -> list[DifficultyResponse]:
        difficulties = [
            build_difficulty_response(difficulty_level)
            for difficulty_level in DifficultyLevel
        ]
        return sorted(difficulties, key=lambda item: item.coefficient)


    async def get_difficulty(self, difficulty_key: DifficultyLevel) -> DifficultyResponse:
        try:
            return build_difficulty_response(difficulty_key)
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Difficulty not found",
            ) from error
