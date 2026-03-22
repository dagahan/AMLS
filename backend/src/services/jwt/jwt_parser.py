from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, status
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from loguru import logger

from src.config import get_app_config
from src.core.utils import TimeTools
from src.models.pydantic import AccessPayload, RefreshPayload
from src.services.auth.sessions_manager import SessionsManager
from src.storage.storage_manager import StorageManager


class JwtParser:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.app_config = get_app_config()
        self.sessions_manager = SessionsManager(storage_manager)
        self.private_key = self._read_key("JWT_PRIVATE_KEY_PATH")
        self.public_key = self._read_key("JWT_PUBLIC_KEY_PATH")
        self.access_token_expire_minutes = int(self.app_config.infra.require("ACCESS_TOKEN_EXPIRE_MINUTES"))
        self.refresh_token_expire_days = int(self.app_config.infra.require("REFRESH_TOKEN_EXPIRE_DAYS"))
        self.algorithm = "RS256"


    def _read_key(self, env_var_name: str) -> str:
        path = self.app_config.resolve_path(str(self.app_config.infra.require(env_var_name)))
        with open(path, "rb") as key_file:
            return key_file.read().decode("utf-8")


    def validate_token(self, token: str) -> dict[str, Any]:
        try:
            return cast("dict[str, Any]", jwt.decode(token, self.public_key, algorithms=[self.algorithm]))
        except JWTError as error:
            logger.error(f"JWT validation error: {error}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            return cast("dict[str, Any]", jwt.decode(token, self.public_key, algorithms=[self.algorithm]))
        except ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        except JWTError as error:
            logger.debug(f"JWT validation error: {error}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        except Exception as error:
            logger.exception(f"Unexpected token decoding error: {error}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


    def generate_access_token(
        self,
        user_id: str,
        session_id: str,
        refresh_token: str | None = None,
        make_old_refresh_token_used: bool = True,
    ) -> str:
        if refresh_token is not None and self.is_refresh_token_in_invalid_list(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token already used",
            )

        expires_at = int((datetime.now(UTC) + timedelta(minutes=self.access_token_expire_minutes)).timestamp())
        payload = AccessPayload(sub=user_id, sid=session_id, exp=expires_at)

        if make_old_refresh_token_used and refresh_token is not None:
            self.make_refresh_token_invalid(refresh_token)

        return cast("str", jwt.encode(payload.model_dump(), self.private_key, algorithm=self.algorithm))


    def generate_refresh_token(
        self,
        user_id: str,
        session_id: str,
        device_signature: str,
        refresh_token: str | None = None,
        make_old_refresh_token_used: bool = True,
    ) -> str:
        if refresh_token is not None and self.is_refresh_token_in_invalid_list(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token already used",
            )

        expires_at = int((datetime.now(UTC) + timedelta(days=self.refresh_token_expire_days)).timestamp())
        payload = RefreshPayload(sub=user_id, sid=session_id, exp=expires_at, dsh=device_signature)

        if make_old_refresh_token_used and refresh_token is not None:
            self.make_refresh_token_invalid(refresh_token)

        return cast("str", jwt.encode(payload.model_dump(), self.private_key, algorithm=self.algorithm))


    def make_refresh_token_invalid(self, refresh_token: str) -> None:
        try:
            claims = cast("dict[str, Any]", jwt.get_unverified_claims(refresh_token))
            expires_at_value = claims.get("exp")
            expires_at = int(expires_at_value) if isinstance(expires_at_value, (int, str)) else None
        except Exception:
            expires_at = None

        now_timestamp = TimeTools.now_time_stamp()
        ttl = max(1, expires_at - now_timestamp) if expires_at is not None else 1
        self.sessions_manager.valkey.set(f"Invalid_refresh:{refresh_token}", "1", ex=ttl)


    def is_refresh_token_in_invalid_list(self, refresh_token: str) -> bool:
        exists = int(self.sessions_manager.valkey.exists(f"Invalid_refresh:{refresh_token}"))
        return exists == 1
