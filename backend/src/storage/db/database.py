from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_app_config
from src.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


logger = get_logger(__name__)


class DataBase:
    def __init__(self) -> None:
        app_config = get_app_config()
        self.engine: AsyncEngine | None = None
        self.async_session: async_sessionmaker[AsyncSession] | None = None

        self.db_host = app_config.postgres_host()
        self.db_port = app_config.infra.postgres_port
        self.db_user = app_config.infra.postgres_user
        self.db_password = app_config.infra.postgres_password
        self.db_name = app_config.infra.postgres_database_name

        self.async_engine_config = (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
        self.sync_engine_config = (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
        self.echo = app_config.infra.database_echo
        self.pool_size = app_config.infra.database_pool_size
        self.max_overflow = app_config.infra.database_max_overflow


    async def init_alchemy_engine(self) -> None:
        self.engine = create_async_engine(
            url=self.async_engine_config,
            echo=self.echo,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
        )
        self.async_session = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        if await self.test_connection():
            logger.info("Connection with database has been established")
            return

        raise RuntimeError("Cannot establish connection with database")


    async def get_session(self) -> AsyncIterator[AsyncSession]:
        if self.async_session is None:
            raise RuntimeError("Database engine is not initialized")

        async with self.async_session() as session:
            yield session


    @asynccontextmanager
    async def session_ctx(self) -> AsyncIterator[AsyncSession]:
        if self.async_session is None:
            raise RuntimeError("Database engine is not initialized")

        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


    async def test_connection(self) -> bool:
        if self.async_session is None:
            raise RuntimeError("Database engine is not initialized")

        try:
            async with self.async_session() as session:
                result = await session.execute(text("SELECT 1"))
                value = cast("int | None", result.scalar())
                return value == 1
        except Exception as error:
            logger.error("Database connection failed", error=str(error))
            return False


    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
