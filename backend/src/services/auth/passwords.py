from __future__ import annotations

import bcrypt

from src.core.logging import get_logger


logger = get_logger(__name__)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError as error:
        logger.error("Password verification failed", error=str(error))
        return False
