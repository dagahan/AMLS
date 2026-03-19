from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from src.fast_api.dependencies import ensure_admin_user, get_current_user
from src.models.alchemy import Difficulty
from src.models.pydantic import DifficultyCreate, DifficultyResponse, DifficultyUpdate, MessageResponse
from src.services.mastery.mastery_cache_manager import MasteryCacheManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.models.alchemy import User


def get_difficulty_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    mastery_cache_manager = MasteryCacheManager()


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


    @router.get("/difficulties", response_model=list[DifficultyResponse], status_code=200)
    async def list_difficulties() -> list[DifficultyResponse]:
        async with db.session_ctx() as session:
            result = await session.execute(select(Difficulty).order_by(Difficulty.coefficient))
            difficulties = result.scalars().all()
            return [DifficultyResponse.model_validate(item) for item in difficulties]


    @router.get("/difficulties/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def get_difficulty(difficulty_id: uuid.UUID) -> DifficultyResponse:
        async with db.session_ctx() as session:
            difficulty = await get_difficulty_or_404(session, difficulty_id)
            return DifficultyResponse.model_validate(difficulty)


    @router.post("/admin/difficulties", response_model=DifficultyResponse, status_code=201)
    async def create_difficulty(
        data: DifficultyCreate,
        user: "User" = Depends(get_current_user),
    ) -> DifficultyResponse:
        ensure_admin_user(user)
        async with db.session_ctx() as session:
            await ensure_name_is_unique(session, data.name)
            difficulty = Difficulty(name=data.name, coefficient=data.coefficient)
            session.add(difficulty)
            await session.flush()
            await session.refresh(difficulty)
        await mastery_cache_manager.bump_problem_mapping_version()
        async with db.session_ctx() as session:
            difficulty = await get_difficulty_or_404(session, difficulty.id)
            return DifficultyResponse.model_validate(difficulty)


    @router.get("/admin/difficulties", response_model=list[DifficultyResponse], status_code=200)
    async def list_admin_difficulties(user: "User" = Depends(get_current_user)) -> list[DifficultyResponse]:
        ensure_admin_user(user)
        return await list_difficulties()


    @router.get("/admin/difficulties/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def get_admin_difficulty(
        difficulty_id: uuid.UUID,
        user: "User" = Depends(get_current_user),
    ) -> DifficultyResponse:
        ensure_admin_user(user)
        return await get_difficulty(difficulty_id)


    @router.patch("/admin/difficulties/{difficulty_id}", response_model=DifficultyResponse, status_code=200)
    async def update_difficulty(
        difficulty_id: uuid.UUID,
        data: DifficultyUpdate,
        user: "User" = Depends(get_current_user),
    ) -> DifficultyResponse:
        ensure_admin_user(user)
        async with db.session_ctx() as session:
            difficulty = await get_difficulty_or_404(session, difficulty_id)

            if data.name is not None:
                await ensure_name_is_unique(session, data.name, current_id=difficulty.id)
                difficulty.name = data.name

            if data.coefficient is not None:
                difficulty.coefficient = data.coefficient

            await session.flush()
            await session.refresh(difficulty)
        await mastery_cache_manager.bump_problem_mapping_version()
        async with db.session_ctx() as session:
            difficulty = await get_difficulty_or_404(session, difficulty_id)
            return DifficultyResponse.model_validate(difficulty)


    @router.delete("/admin/difficulties/{difficulty_id}", response_model=MessageResponse, status_code=200)
    async def delete_difficulty(
        difficulty_id: uuid.UUID,
        user: "User" = Depends(get_current_user),
    ) -> MessageResponse:
        ensure_admin_user(user)
        async with db.session_ctx() as session:
            difficulty = await get_difficulty_or_404(session, difficulty_id)
            await session.delete(difficulty)
        await mastery_cache_manager.bump_problem_mapping_version()
        return MessageResponse(message="Difficulty deleted")


    return router
