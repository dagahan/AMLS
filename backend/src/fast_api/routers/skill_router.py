from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from src.db.enums import UserRole
from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext, MessageResponse, SkillCreate, SkillResponse, SkillUpdate
from src.services.catalog import SkillService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_skill_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    skill_service = SkillService(db)


    @router.get("/skills", response_model=list[SkillResponse], status_code=200)
    async def list_skills(
        auth: AuthContext = Depends(require_role()),
    ) -> list[SkillResponse]:
        return await skill_service.list_skills()


    @router.get("/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def get_skill(
        skill_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> SkillResponse:
        return await skill_service.get_skill(skill_id)


    @router.post("/admin/skills", response_model=SkillResponse, status_code=201)
    async def create_skill(
        data: SkillCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SkillResponse:
        return await skill_service.create_skill(data)


    @router.get("/admin/skills", response_model=list[SkillResponse], status_code=200)
    async def list_admin_skills(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[SkillResponse]:
        return await skill_service.list_skills()


    @router.get("/admin/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def get_admin_skill(
        skill_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SkillResponse:
        return await skill_service.get_skill(skill_id)


    @router.patch("/admin/skills/{skill_id}", response_model=SkillResponse, status_code=200)
    async def update_skill(
        skill_id: uuid.UUID,
        data: SkillUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> SkillResponse:
        return await skill_service.update_skill(skill_id, data)


    @router.delete("/admin/skills/{skill_id}", response_model=MessageResponse, status_code=200)
    async def delete_skill(
        skill_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> MessageResponse:
        await skill_service.delete_skill(skill_id)
        return MessageResponse(message="Skill deleted")


    return router
