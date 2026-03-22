import hashlib
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import bcrypt
from loguru import logger

from src.config import get_app_config


class FileSystemTools:
    @staticmethod
    def ensure_directory_exists(directory: str) -> None:
        Path(directory).mkdir(parents=True, exist_ok=True)


class StringTools:
    @staticmethod
    def hash_string(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PasswordTools:
    @staticmethod
    def hash_password(value: str) -> str:
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


    @staticmethod
    def verify_password(plain_value: str, hashed_value: str) -> bool:
        try:
            return bcrypt.checkpw(plain_value.encode("utf-8"), hashed_value.encode("utf-8"))
        except ValueError as error:
            logger.error(f"Password verification failed: {error}")
            return False


class TimeTools:
    @staticmethod
    def now_time_zone() -> datetime:
        time_zone_name = str(get_app_config().infra.get("TZ", "UTC"))
        try:
            time_zone = ZoneInfo(time_zone_name)
        except Exception:
            time_zone = ZoneInfo("UTC")
        return datetime.now(time_zone)


    @staticmethod
    def now_time_stamp() -> int:
        return int(TimeTools.now_time_zone().timestamp())
