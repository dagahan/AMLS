from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.db.enums import UserRole
from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.entrance_test import (
    EntranceTestSessionResponse,
    build_entrance_test_session_response,
)

if TYPE_CHECKING:
    from src.models.alchemy.entrance_test import EntranceTestSession
    from src.models.alchemy.user import User


class UserResponse(AmlsSchema):
    id: UUID
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None
    role: UserRole
    is_active: bool
    entrance_test: EntranceTestSessionResponse | None = None


class AvatarSnapshot(AmlsSchema):
    user_id: UUID
    avatar_url: str | None


def build_user_response(
    user: "User",
    entrance_test_session: "EntranceTestSession | None" = None,
) -> UserResponse:
    loaded_entrance_test_session = entrance_test_session
    if loaded_entrance_test_session is None:
        loaded_entrance_test_session = user.__dict__.get("entrance_test_session")

    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        role=user.role,
        is_active=user.is_active,
        entrance_test=(
            build_entrance_test_session_response(loaded_entrance_test_session)
            if loaded_entrance_test_session is not None
            else None
        ),
    )
