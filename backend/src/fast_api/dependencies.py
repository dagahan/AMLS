from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from src.db.enums import UserRole
from src.models.alchemy import User
from src.models.pydantic import AuthContext, ClientContext, UserResponse
from src.services.auth.auth_service import AuthService

if TYPE_CHECKING:
    from src.db.database import DataBase


bearer_scheme = HTTPBearer(auto_error=False)


def require_role(role: UserRole | None = None) -> Callable[..., Awaitable[AuthContext]]:
    async def resolve_auth_context(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> AuthContext:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization required",
            )

        db = cast("DataBase", request.app.state.database)
        auth_service = AuthService(db)
        payload = await auth_service.validate_access_token(credentials.credentials)

        try:
            user_id = uuid.UUID(payload.sub)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            ) from error

        async with db.session_ctx() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive",
            )

        if role is not None and user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{role.value.capitalize()} role required",
            )

        return AuthContext(
            user=UserResponse.model_validate(user),
            payload=payload,
        )

    return resolve_auth_context


def parse_optional_uuid(raw_value: str | None, field_name: str) -> uuid.UUID | None:
    if raw_value is None or raw_value == "":
        return None

    try:
        return uuid.UUID(raw_value)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a valid UUID",
        ) from error


def build_client_context(request: Request) -> ClientContext:
    return ClientContext(
        user_agent=request.headers.get("user-agent", "postman"),
        client_id=request.headers.get("x-client-id", "default-client"),
        local_system_time_zone=request.headers.get("x-time-zone", "UTC"),
        platform=request.headers.get("x-platform", "desktop"),
        ip=request.client.host if request.client is not None else "127.0.0.1",
    )


def build_storage_file_url(request: Request, storage_key: str) -> str:
    return str(request.url_for("get_stored_file", storage_key=storage_key))
