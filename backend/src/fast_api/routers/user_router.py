from __future__ import annotations

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext
from src.models.pydantic.user import UserProfileUpdateRequest, UserResponse
from src.services.user import UserService
from src.storage.storage_manager import StorageManager


def get_user_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["users"])
    user_service = UserService(storage_manager)


    @router.patch("/users/me", response_model=UserResponse, status_code=200)
    async def update_current_user_profile(
        data: UserProfileUpdateRequest,
        auth: AuthContext = Depends(require_role()),
    ) -> UserResponse:
        return await user_service.update_profile(auth.user.id, data)


    return router
