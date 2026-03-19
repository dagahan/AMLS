from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from src.db.enums import UserRole
from src.models.alchemy import User
from src.services.auth.auth_service import AuthService
from src.services.jwt.jwt_parser import JwtParser

if TYPE_CHECKING:
    from src.db.database import DataBase


bearer_scheme = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    db = cast("DataBase", request.app.state.database)
    auth_service = AuthService(db)
    jwt_parser = JwtParser()

    await auth_service.validate_access_token(credentials.credentials)
    payload = jwt_parser.decode_token(credentials.credentials)

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        parsed_user_id = uuid.UUID(user_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        ) from error

    async with db.session_ctx() as session:
        result = await session.execute(select(User).where(User.id == parsed_user_id))
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    return user


def ensure_admin_user(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin rights required",
        )


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
