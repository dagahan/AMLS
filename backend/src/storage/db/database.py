from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_app_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class DataBase:
    def __init__(self) -> None:
        app_config = get_app_config()
        self.engine: AsyncEngine | None = None
        self.async_session: async_sessionmaker[AsyncSession] | None = None

        self.db_host = app_config.service_host("postgres")
        self.db_port = app_config.service_port("postgres")
        self.db_user = str(app_config.infra.require("POSTGRES_USER"))
        self.db_password = str(app_config.infra.require("POSTGRES_PASSWORD"))
        self.db_name = str(app_config.infra.require("POSTGRES_DB"))

        self.async_engine_config = (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
        self.sync_engine_config = (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
        self.echo = bool(int(app_config.infra.require("DB_ECHO")))
        self.pool_size = int(app_config.infra.require("DB_POOL_SIZE"))
        self.max_overflow = int(app_config.infra.require("DB_MAX_OVERFLOW"))


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
            logger.error(f"Database connection failed: {error}")
            return False


    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
