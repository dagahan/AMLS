from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from loguru import logger

from src.core.clients import get_valkey_client
from src.core.utils import EnvTools, StringTools, TimeTools
from src.models.pydantic import ClientContext, SessionData


class SessionsManager:
    def __init__(self) -> None:
        self.session_max_life_days = int(EnvTools.required_load_env_var("SESSIONS_MAX_LIFE_DAYS"))
        self.session_inactive_days = int(EnvTools.required_load_env_var("SESSIONS_INACTIVE_DAYS"))
        self.valkey = get_valkey_client()


    def _days_to_seconds(self, days: int) -> int:
        return days * 24 * 60 * 60


    def _clamped_ttl_seconds(self, now_timestamp: int, max_life_timestamp: int) -> int:
        remaining_lifetime = max(0, max_life_timestamp - now_timestamp)
        return min(remaining_lifetime, self._days_to_seconds(self.session_inactive_days))


    def create_session(self, user_id: str, client_context: ClientContext) -> dict[str, str]:
        session_id = uuid.uuid4()
        session_key = f"Session:{session_id}"

        issued_at = TimeTools.now_time_stamp()
        max_life_timestamp = issued_at + self._days_to_seconds(self.session_max_life_days)
        device_signature = StringTools.hash_string(
            (
                f"{client_context.user_agent}"
                f"{client_context.client_id}"
                f"{client_context.local_system_time_zone}"
                f"{client_context.platform}"
            )
        )
        ip_signature = StringTools.hash_string(client_context.ip)

        session_data = SessionData(
            sub=user_id,
            iat=issued_at,
            mtl=max_life_timestamp,
            dsh=device_signature,
            ish=ip_signature,
        )

        payload = {key: str(value) for key, value in session_data.model_dump().items()}
        self.valkey.hset(session_key, mapping=payload)

        ttl = self._clamped_ttl_seconds(issued_at, max_life_timestamp)
        if ttl > 0:
            self.valkey.expire(session_key, ttl)
        else:
            self.valkey.delete(session_key)

        logger.debug(f"Created session {session_id} for user {user_id}")

        return {
            "session_id": str(session_id),
            "iat": str(issued_at),
            "mtl": str(max_life_timestamp),
            "dsh": device_signature,
        }


    def touch_session(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False

        now_timestamp = TimeTools.now_time_stamp()
        ttl = self._clamped_ttl_seconds(now_timestamp, session.mtl)
        if ttl <= 0:
            self.valkey.delete(f"Session:{session_id}")
            return False

        self.valkey.expire(f"Session:{session_id}", ttl)
        return True


    def delete_session(self, session_id: str) -> None:
        self.valkey.delete(f"Session:{session_id}")


    def delete_all_sessions_for_user(self, user_id: str) -> int:
        deleted_count = 0
        cursor = 0

        while True:
            cursor, keys = self.valkey.scan(
                cursor=cursor,
                match="Session:*",
                count=1000,
            )

            if keys:
                pipeline = self.valkey.pipeline()
                for key in keys:
                    pipeline.hget(key, "sub")
                user_ids = pipeline.execute()

                keys_to_delete = [
                    key
                    for key, current_user_id in zip(keys, user_ids, strict=False)
                    if current_user_id == user_id
                ]

                if keys_to_delete:
                    delete_pipeline = self.valkey.pipeline()
                    for key in keys_to_delete:
                        delete_pipeline.delete(key)
                    deleted_results = delete_pipeline.execute()
                    deleted_count += sum(1 for item in deleted_results if item)

            if cursor == 0:
                break

        return deleted_count


    def is_session_exists(self, session_id: str) -> bool:
        return self.get_session(session_id) is not None


    def get_session(self, session_id: str) -> SessionData | None:
        raw_data = self.valkey.hgetall(f"Session:{session_id}")
        if not raw_data:
            return None

        try:
            return self.validate_session(raw_data)
        except Exception as error:
            logger.warning(f"Session {session_id} failed validation: {error}")
            return None


    def validate_session(self, raw_data: Mapping[str, Any] | None) -> SessionData | None:
        if raw_data is None:
            return None
        return SessionData.model_validate(raw_data)
