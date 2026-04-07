from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from src.core.logging import get_logger
from src.models.alchemy import User
from src.models.pydantic.user import UserProfileUpdateRequest, UserResponse, build_user_response
from src.storage.storage_manager import StorageManager


logger = get_logger(__name__)


class UserService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def update_profile(
        self,
        user_id: uuid.UUID,
        data: UserProfileUpdateRequest,
    ) -> UserResponse:
        async with self.storage_manager.session_ctx() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            user.first_name = data.first_name
            user.last_name = data.last_name
            await session.flush()
            await session.refresh(user)

            logger.info(
                "Updated user profile",
                user_id=str(user.id),
            )
            return build_user_response(user)
