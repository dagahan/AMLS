from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from src.db.enums import UserRole
from src.fast_api.dependencies import require_role
from src.models.alchemy import Skill
from src.models.pydantic import AuthContext, MessageResponse, SkillCreate, SkillResponse, SkillUpdate
from src.services.mastery.mastery_cache_manager import MasteryCacheManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


def get_skill_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    mastery_cache_manager = MasteryCacheManager()


    async def get_skill_or_404(session: "AsyncSession", skill_id: uuid.UUID) -> Skill:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
        return skill


    async def ensure_skill_name_is_unique(
        session: "AsyncSession",
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(Skill).where(Skill.name == name))
        skill = result.scalar_one_or_none()
        if skill is not None and skill.id != current_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill name must be unique")


    @router.get("/skills", response_model=list[SkillResponse], status_code=200)
    async def list_skills(
        auth: AuthContext = Depends(require_role()),
    ) -> list[SkillResponse]:
        async with db.session_ctx() as session:
            result = await session.execute(select(Skill).order_by(Skill.name))
            skills = result.scalars().all()
        return [SkillResponse.model_validate(item) for item in skills]


    @router.get("/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def get_skill(
        skill_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> SkillResponse:
        async with db.session_ctx() as session:
            skill = await get_skill_or_404(session, skill_id)
        return SkillResponse.model_validate(skill)


    @router.post("/admin/skills", response_model=SkillResponse, status_code=201)
    async def create_skill(
        data: SkillCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SkillResponse:
        async with db.session_ctx() as session:
            await ensure_skill_name_is_unique(session, data.name)
            skill = Skill(name=data.name)
            session.add(skill)
            await session.flush()
            await session.refresh(skill)
        await mastery_cache_manager.bump_taxonomy_version()
        return SkillResponse.model_validate(skill)


    @router.get("/admin/skills", response_model=list[SkillResponse], status_code=200)
    async def list_admin_skills(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[SkillResponse]:
        return await list_skills(auth)


    @router.get("/admin/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def get_admin_skill(
        skill_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SkillResponse:
        return await get_skill(skill_id, auth)


    @router.patch("/admin/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def update_skill(
        skill_id: uuid.UUID,
        data: SkillUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SkillResponse:
        async with db.session_ctx() as session:
            skill = await get_skill_or_404(session, skill_id)
            if data.name is not None:
                await ensure_skill_name_is_unique(session, data.name, current_id=skill.id)
                skill.name = data.name
            await session.flush()
            await session.refresh(skill)
        return SkillResponse.model_validate(skill)


    @router.delete("/admin/skills/{skill_id}", response_model=MessageResponse, status_code=200)
    async def delete_skill(
        skill_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        async with db.session_ctx() as session:
            skill = await get_skill_or_404(session, skill_id)
            await session.delete(skill)
        await mastery_cache_manager.bump_taxonomy_version()
        return MessageResponse(message="Skill deleted")


    return router
