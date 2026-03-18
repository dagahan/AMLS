from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from src.db.models import Skill, Subskill
from src.fast_api.dependencies import build_current_admin_dependency, parse_optional_uuid
from src.pydantic_schemas import (
    MessageResponse,
    SkillCreate,
    SkillResponse,
    SkillUpdate,
    SubskillCreate,
    SubskillResponse,
    SubskillUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.db.models import User


def get_skill_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    current_admin = build_current_admin_dependency(db)


    async def get_skill_or_404(session: "AsyncSession", skill_id: uuid.UUID) -> Skill:
        result = await session.execute(select(Skill).where(Skill.id == skill_id))
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
        return skill


    async def get_subskill_or_404(session: "AsyncSession", subskill_id: uuid.UUID) -> Subskill:
        result = await session.execute(select(Subskill).where(Subskill.id == subskill_id))
        subskill = result.scalar_one_or_none()
        if subskill is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subskill not found")
        return subskill


    async def ensure_skill_name_is_unique(
        session: "AsyncSession",
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(Skill).where(Skill.name == name))
        skill = result.scalar_one_or_none()
        if skill is not None and skill.id != current_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill name must be unique")


    async def ensure_subskill_name_is_unique(
        session: "AsyncSession",
        skill_id: uuid.UUID,
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(
            select(Subskill).where(Subskill.skill_id == skill_id, Subskill.name == name)
        )
        subskill = result.scalar_one_or_none()
        if subskill is not None and subskill.id != current_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subskill name must be unique inside the skill",
            )


    @router.get("/skills", response_model=list[SkillResponse], status_code=200)
    async def list_skills() -> list[SkillResponse]:
        async with db.session_ctx() as session:
            result = await session.execute(select(Skill).order_by(Skill.name))
            skills = result.scalars().all()
            return [SkillResponse.model_validate(item) for item in skills]


    @router.get("/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def get_skill(skill_id: uuid.UUID) -> SkillResponse:
        async with db.session_ctx() as session:
            skill = await get_skill_or_404(session, skill_id)
            return SkillResponse.model_validate(skill)


    @router.get("/subskills", response_model=list[SubskillResponse], status_code=200)
    async def list_subskills(
        skill_id: str | None = Query(default=None),
    ) -> list[SubskillResponse]:
        parsed_skill_id = parse_optional_uuid(skill_id, "skill_id")
        async with db.session_ctx() as session:
            statement = select(Subskill).order_by(Subskill.name)
            if parsed_skill_id is not None:
                statement = statement.where(Subskill.skill_id == parsed_skill_id)
            result = await session.execute(statement)
            subskills = result.scalars().all()
            return [SubskillResponse.model_validate(item) for item in subskills]


    @router.get("/subskills/{subskill_id}", response_model=SubskillResponse, status_code=200)
    async def get_subskill(subskill_id: uuid.UUID) -> SubskillResponse:
        async with db.session_ctx() as session:
            subskill = await get_subskill_or_404(session, subskill_id)
            return SubskillResponse.model_validate(subskill)


    @router.post("/admin/skills", response_model=SkillResponse, status_code=201)
    async def create_skill(
        data: SkillCreate,
        _: "User" = Depends(current_admin),
    ) -> SkillResponse:
        async with db.session_ctx() as session:
            await ensure_skill_name_is_unique(session, data.name)
            skill = Skill(name=data.name)
            session.add(skill)
            await session.flush()
            await session.refresh(skill)
            return SkillResponse.model_validate(skill)


    @router.get("/admin/skills", response_model=list[SkillResponse], status_code=200)
    async def list_admin_skills(_: "User" = Depends(current_admin)) -> list[SkillResponse]:
        return await list_skills()


    @router.get("/admin/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def get_admin_skill(
        skill_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> SkillResponse:
        return await get_skill(skill_id)


    @router.patch("/admin/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def update_skill(
        skill_id: uuid.UUID,
        data: SkillUpdate,
        _: "User" = Depends(current_admin),
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
        _: "User" = Depends(current_admin),
    ) -> MessageResponse:
        async with db.session_ctx() as session:
            skill = await get_skill_or_404(session, skill_id)
            await session.delete(skill)
            return MessageResponse(message="Skill deleted")


    @router.post("/admin/subskills", response_model=SubskillResponse, status_code=201)
    async def create_subskill(
        data: SubskillCreate,
        _: "User" = Depends(current_admin),
    ) -> SubskillResponse:
        async with db.session_ctx() as session:
            await get_skill_or_404(session, data.skill_id)
            await ensure_subskill_name_is_unique(session, data.skill_id, data.name)
            subskill = Subskill(skill_id=data.skill_id, name=data.name)
            session.add(subskill)
            await session.flush()
            await session.refresh(subskill)
            return SubskillResponse.model_validate(subskill)


    @router.get("/admin/subskills", response_model=list[SubskillResponse], status_code=200)
    async def list_admin_subskills(
        skill_id: str | None = Query(default=None),
        _: "User" = Depends(current_admin),
    ) -> list[SubskillResponse]:
        return await list_subskills(skill_id)


    @router.get("/admin/subskills/{subskill_id}", response_model=SubskillResponse, status_code=200)
    async def get_admin_subskill(
        subskill_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> SubskillResponse:
        return await get_subskill(subskill_id)


    @router.patch("/admin/subskills/{subskill_id}", response_model=SubskillResponse, status_code=200)
    async def update_subskill(
        subskill_id: uuid.UUID,
        data: SubskillUpdate,
        _: "User" = Depends(current_admin),
    ) -> SubskillResponse:
        async with db.session_ctx() as session:
            subskill = await get_subskill_or_404(session, subskill_id)

            if data.skill_id is not None:
                await get_skill_or_404(session, data.skill_id)
                subskill.skill_id = data.skill_id
                if data.name is None:
                    await ensure_subskill_name_is_unique(
                        session,
                        data.skill_id,
                        subskill.name,
                        current_id=subskill.id,
                    )

            if data.name is not None:
                await ensure_subskill_name_is_unique(
                    session,
                    data.skill_id or subskill.skill_id,
                    data.name,
                    current_id=subskill.id,
                )
                subskill.name = data.name

            await session.flush()
            await session.refresh(subskill)
            return SubskillResponse.model_validate(subskill)


    @router.delete("/admin/subskills/{subskill_id}", response_model=MessageResponse, status_code=200)
    async def delete_subskill(
        subskill_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> MessageResponse:
        async with db.session_ctx() as session:
            subskill = await get_subskill_or_404(session, subskill_id)
            await session.delete(subskill)
            return MessageResponse(message="Subskill deleted")


    return router
