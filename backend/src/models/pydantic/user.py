from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema
from src.storage.db.enums import UserRole

if TYPE_CHECKING:
    from src.models.alchemy.user import User


class UserResponse(AmlsSchema):
    id: UUID
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None
    role: UserRole
    is_active: bool


class AvatarSnapshot(AmlsSchema):
    user_id: UUID
    avatar_url: str | None


class UserProfileUpdateRequest(AmlsSchema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


def build_user_response(user: "User") -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        role=user.role,
        is_active=user.is_active,
    )
