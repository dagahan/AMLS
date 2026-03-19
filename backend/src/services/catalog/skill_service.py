from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from src.models.alchemy import Skill
from src.models.pydantic import SkillCreate, SkillResponse, SkillUpdate
from src.valkey.mastery_cache import MasteryCache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class SkillService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.mastery_cache = MasteryCache()


    async def list_skills(self) -> list[SkillResponse]:
        async with self.db.session_ctx() as session:
            result = await session.execute(select(Skill).order_by(Skill.name))
            skills = result.scalars().all()
        return [SkillResponse.model_validate(item) for item in skills]


    async def get_skill(self, skill_id: uuid.UUID) -> SkillResponse:
        async with self.db.session_ctx() as session:
            skill = await self._get_skill_or_404(session, skill_id)
            return SkillResponse.model_validate(skill)


    async def create_skill(self, data: SkillCreate) -> SkillResponse:
        async with self.db.session_ctx() as session:
            await self._ensure_skill_name_is_unique(session, data.name)
            skill = Skill(name=data.name)
            session.add(skill)
            await session.flush()
            await session.refresh(skill)
            response = SkillResponse.model_validate(skill)
        await self.mastery_cache.bump_taxonomy_version()
        return response


    async def update_skill(self, skill_id: uuid.UUID, data: SkillUpdate) -> SkillResponse:
        async with self.db.session_ctx() as session:
            skill = await self._get_skill_or_404(session, skill_id)
            if data.name is not None:
                await self._ensure_skill_name_is_unique(session, data.name, current_id=skill.id)
                skill.name = data.name
            await session.flush()
            await session.refresh(skill)
            response = SkillResponse.model_validate(skill)
        return response


    async def delete_skill(self, skill_id: uuid.UUID) -> None:
        async with self.db.session_ctx() as session:
            skill = await self._get_skill_or_404(session, skill_id)
            await session.delete(skill)
        await self.mastery_cache.bump_taxonomy_version()


    async def _get_skill_or_404(
        self,
        session: "AsyncSession",
        skill_id: uuid.UUID,
    ) -> Skill:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
        return skill


    async def _ensure_skill_name_is_unique(
        self,
        session: "AsyncSession",
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(Skill).where(Skill.name == name))
        skill = result.scalar_one_or_none()
        if skill is not None and skill.id != current_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill name must be unique")
