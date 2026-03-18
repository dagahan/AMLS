from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import select

from src.core.utils import PasswordTools
from src.db.enums import UserRole
from src.db.models import User
from src.pydantic_schemas import ClientContext, RegisterRequest, TokenPairResponse
from src.services.auth.sessions_manager import SessionsManager
from src.services.jwt.jwt_parser import JwtParser
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from src.db.database import DataBase


class AuthService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.jwt_parser = JwtParser()
        self.sessions_manager = SessionsManager()


    async def authenticate_user(self, email: str, password: str) -> User:
        async with self.db.session_ctx() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

        if user is None or not PasswordTools.verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account deactivated",
            )

        return user


    @transactional
    async def register_user(self, data: RegisterRequest) -> User:
        return await execute_atomic_step(
            action=lambda: self._create_user_record(data),
            rollback=lambda user: self._delete_user_record(user.id),
            step_name="create_user_record",
        )


    async def _create_user_record(self, data: RegisterRequest) -> User:
        async with self.db.session_ctx() as session:
            result = await session.execute(select(User).where(User.email == data.email))
            existing_user = result.scalar_one_or_none()
            if existing_user is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

            user = User(
                email=str(data.email),
                first_name=data.first_name,
                last_name=data.last_name,
                avatar_url=data.avatar_url,
                hashed_password=PasswordTools.hash_password(data.password.get_secret_value()),
                role=UserRole.STUDENT,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)

        return user


    async def _delete_user_record(self, user_id: object) -> None:
        async with self.db.session_ctx() as session:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)


    async def login_user(self, email: str, password: str, client_context: ClientContext) -> TokenPairResponse:
        user = await self.authenticate_user(email, password)
        user_id = str(user.id)
        session_data = self.sessions_manager.create_session(user_id, client_context)
        session_id = session_data["session_id"]
        device_signature = session_data["dsh"]

        refresh_token = self.jwt_parser.generate_refresh_token(
            user_id=user_id,
            session_id=session_id,
            device_signature=device_signature,
            make_old_refresh_token_used=False,
        )
        access_token = self.jwt_parser.generate_access_token(
            user_id=user_id,
            session_id=session_id,
            refresh_token=refresh_token,
            make_old_refresh_token_used=False,
        )

        return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


    async def validate_access_token(self, access_token: str) -> bool:
        payload: dict[str, Any] = self.jwt_parser.decode_token(access_token)

        user_id = payload.get("sub")
        session_id = payload.get("sid")
        expires_at = payload.get("exp")

        if not isinstance(user_id, str) or not isinstance(session_id, str) or not expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        session = self.sessions_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session expired",
            )

        if session.sub != user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not match session user",
            )

        if not self.sessions_manager.touch_session(session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session expired",
            )

        return True


    async def refresh_tokens(self, refresh_token: str) -> TokenPairResponse:
        payload = self.jwt_parser.decode_token(refresh_token)

        session_id = payload.get("sid")
        user_id = payload.get("sub")
        device_signature = payload.get("dsh")

        if not isinstance(session_id, str) or not isinstance(user_id, str) or not isinstance(device_signature, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        session = self.sessions_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session expired",
            )

        if session.sub != user_id or session.dsh != device_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not match session",
            )

        new_refresh_token = self.jwt_parser.generate_refresh_token(
            user_id=user_id,
            session_id=session_id,
            device_signature=device_signature,
            refresh_token=refresh_token,
            make_old_refresh_token_used=True,
        )
        access_token = self.jwt_parser.generate_access_token(
            user_id=user_id,
            session_id=session_id,
            make_old_refresh_token_used=False,
        )

        return TokenPairResponse(access_token=access_token, refresh_token=new_refresh_token)
