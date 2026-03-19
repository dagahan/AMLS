from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from src.db.enums import UserRole
from src.models.alchemy import User
from src.models.pydantic import (
    AccessValidationResponse,
    AuthUserResponse,
    ClientContext,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
    ValidateAccessRequest,
)
from src.services.auth.auth_service import AuthService
from src.services.jwt.jwt_parser import JwtParser

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.db.database import DataBase


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


def build_current_user_dependency(db: "DataBase") -> "Callable[..., object]":
    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    ) -> User:
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


    return get_current_user


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


def get_auth_router(db: "DataBase") -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])
    auth_service = AuthService(db)
    current_user = build_current_user_dependency(db)


    @router.post("/register", response_model=UserResponse, status_code=201)
    async def register(data: RegisterRequest) -> UserResponse:
        user = await auth_service.register_user(data)
        return UserResponse.model_validate(user)


    @router.post("/login", response_model=TokenPairResponse, status_code=201)
    async def login(data: LoginRequest, request: Request) -> TokenPairResponse:
        client_context = build_client_context(request)
        return await auth_service.login_user(
            email=str(data.email),
            password=data.password.get_secret_value(),
            client_context=client_context,
        )


    @router.post("/refresh", response_model=TokenPairResponse, status_code=201)
    async def refresh(data: RefreshRequest) -> TokenPairResponse:
        return await auth_service.refresh_tokens(data.refresh_token)


    @router.post("/access/validate", response_model=AccessValidationResponse, status_code=200)
    async def validate_access(data: ValidateAccessRequest) -> AccessValidationResponse:
        is_valid = await auth_service.validate_access_token(data.access_token)
        return AccessValidationResponse(valid=is_valid)


    @router.get("/me", response_model=AuthUserResponse, status_code=200)
    async def get_me(user: User = Depends(current_user)) -> AuthUserResponse:
        return AuthUserResponse(user=user)


    return router
