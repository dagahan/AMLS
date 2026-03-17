from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from src.db.models import Difficulty
from src.fast_api.dependencies import build_current_admin_dependency
from src.pydantic_schemas import DifficultyCreate, DifficultyResponse, DifficultyUpdate, MessageResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.db.models import User


def get_difficulty_router(db: "DataBase") -> APIRouter:
    router = APIRouter(prefix="/admin/difficulties", tags=["admin-difficulties"])
    current_admin = build_current_admin_dependency(db)


    async def get_difficulty_or_404(session: "AsyncSession", difficulty_id: uuid.UUID) -> Difficulty:
        result = await session.execute(select(Difficulty).where(Difficulty.id == difficulty_id))
        difficulty = result.scalar_one_or_none()
        if difficulty is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Difficulty not found")
        return difficulty


    async def ensure_name_is_unique(
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


    @router.post("", response_model=DifficultyResponse, status_code=201)
    async def create_difficulty(
        data: DifficultyCreate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> DifficultyResponse:
        await ensure_name_is_unique(session, data.name)

        difficulty = Difficulty(
            name=data.name,
            coefficient_beta_bernoulli=data.coefficient_beta_bernoulli,
        )
        session.add(difficulty)
        await session.commit()
        await session.refresh(difficulty)
        return DifficultyResponse.model_validate(difficulty)


    @router.get("", response_model=list[DifficultyResponse], status_code=200)
    async def list_difficulties(
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> list[DifficultyResponse]:
        result = await session.execute(select(Difficulty).order_by(Difficulty.name))
        difficulties = result.scalars().all()
        return [DifficultyResponse.model_validate(item) for item in difficulties]


    @router.get("/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def get_difficulty(
        difficulty_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> DifficultyResponse:
        difficulty = await get_difficulty_or_404(session, difficulty_id)
        return DifficultyResponse.model_validate(difficulty)


    @router.patch("/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def update_difficulty(
        difficulty_id: uuid.UUID,
        data: DifficultyUpdate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> DifficultyResponse:
        difficulty = await get_difficulty_or_404(session, difficulty_id)

        if data.name is not None:
            await ensure_name_is_unique(session, data.name, current_id=difficulty.id)
            difficulty.name = data.name

        if data.coefficient_beta_bernoulli is not None:
            difficulty.coefficient_beta_bernoulli = data.coefficient_beta_bernoulli

        await session.commit()
        await session.refresh(difficulty)
        return DifficultyResponse.model_validate(difficulty)


    @router.delete("/{difficulty_id}", response_model=MessageResponse, status_code=200)
    async def delete_difficulty(
        difficulty_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> MessageResponse:
        difficulty = await get_difficulty_or_404(session, difficulty_id)
        await session.delete(difficulty)
        await session.commit()
        return MessageResponse(message="Difficulty deleted")


    return router
