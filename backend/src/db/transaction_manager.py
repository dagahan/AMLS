from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class TransactionManager:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    @asynccontextmanager
    async def session(self) -> AsyncIterator["AsyncSession"]:
        if self.db.async_session is None:
            raise RuntimeError("Database engine is not initialized")

        async with self.db.async_session() as session:
            async with session.begin():
                yield session
