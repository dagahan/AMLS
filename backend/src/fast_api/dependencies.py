from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from src.db.enums import UserRole
from src.db.models import User
from src.db.transaction_manager import TransactionManager
from src.services.auth.auth_service import AuthService
from src.services.jwt.jwt_parser import JwtParser

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


def build_current_user_dependency(db: "DataBase") -> "Callable[..., object]":
    bearer_scheme = HTTPBearer()
    auth_service = AuthService(db)
    jwt_parser = JwtParser()
    transaction_manager = TransactionManager(db)


    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    ) -> User:
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
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            )

        async with transaction_manager.session() as session:
            result = await session.execute(select(User).where(User.id == parsed_user_id))
            user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

        return user


    return get_current_user


def parse_optional_uuid(raw_value: str | None, field_name: str) -> uuid.UUID | None:
    if raw_value is None or raw_value == "":
        return None

    try:
        return uuid.UUID(raw_value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a valid UUID",
        )


def build_current_admin_dependency(db: "DataBase") -> "Callable[..., object]":
    current_user_dependency = build_current_user_dependency(db)


    async def get_current_admin(current_user: User = Depends(current_user_dependency)) -> User:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin rights required",
            )
        return current_user


    return get_current_admin
