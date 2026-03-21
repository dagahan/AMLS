from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from src.models.alchemy import Difficulty
from src.models.pydantic import DifficultyCreate, DifficultyResponse, DifficultyUpdate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class DifficultyService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    async def list_difficulties(self) -> list[DifficultyResponse]:
        async with self.db.session_ctx() as session:
            result = await session.execute(select(Difficulty).order_by(Difficulty.coefficient))
            difficulties = result.scalars().all()
        return [DifficultyResponse.model_validate(item) for item in difficulties]


    async def get_difficulty(self, difficulty_id: uuid.UUID) -> DifficultyResponse:
        async with self.db.session_ctx() as session:
            difficulty = await self._get_difficulty_or_404(session, difficulty_id)
            return DifficultyResponse.model_validate(difficulty)


    async def create_difficulty(self, data: DifficultyCreate) -> DifficultyResponse:
        async with self.db.session_ctx() as session:
            await self._ensure_name_is_unique(session, data.name)
            difficulty = Difficulty(name=data.name, coefficient=data.coefficient)
            session.add(difficulty)
            await session.flush()
            await session.refresh(difficulty)
            return DifficultyResponse.model_validate(difficulty)


    async def update_difficulty(
        self,
        difficulty_id: uuid.UUID,
        data: DifficultyUpdate,
    ) -> DifficultyResponse:
        async with self.db.session_ctx() as session:
            difficulty = await self._get_difficulty_or_404(session, difficulty_id)

            if data.name is not None:
                await self._ensure_name_is_unique(session, data.name, current_id=difficulty.id)
                difficulty.name = data.name

            if data.coefficient is not None:
                difficulty.coefficient = data.coefficient

            await session.flush()
            await session.refresh(difficulty)
            return DifficultyResponse.model_validate(difficulty)


    async def delete_difficulty(self, difficulty_id: uuid.UUID) -> None:
        async with self.db.session_ctx() as session:
            difficulty = await self._get_difficulty_or_404(session, difficulty_id)
            await session.delete(difficulty)


    async def _get_difficulty_or_404(
        self,
        session: "AsyncSession",
        difficulty_id: uuid.UUID,
    ) -> Difficulty:
        result = await session.execute(select(Difficulty).where(Difficulty.id == difficulty_id))
        difficulty = result.scalar_one_or_none()
        if difficulty is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Difficulty not found")
        return difficulty


    async def _ensure_name_is_unique(
        self,
        session: "AsyncSession",
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(Difficulty).where(Difficulty.name == name))
        difficulty = result.scalar_one_or_none()
        if difficulty is not None and difficulty.id != current_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Difficulty name must be unique",
            )
