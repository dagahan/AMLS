from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import os
from pathlib import Path
import sys
import uuid

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.config import bootstrap_config
from src.bootstrap import bootstrap_demo_course
from src.fast_api.fastapi_server import create_application
from src.models.alchemy import Base, Course, User
from src.models.pydantic import TokenPairResponse
from src.services.auth.passwords import hash_password
from src.storage.storage_manager import StorageManager
from src.storage.db.database import DataBase
from src.storage.db.enums import UserRole
from src.storage.db.reference_problem_bank import load_reference_problem_bank
from src.storage.db.reference_sync import sync_reference_data


@pytest.fixture(scope="session", autouse=True)
def bootstrap_environment() -> Iterator[None]:
    os.environ.setdefault("LMS_BASE_URL", "http://127.0.0.1:1234/v1")
    os.environ.setdefault("LMS_API_KEY", "lm-studio")
    os.environ.setdefault("LMS_MODEL", "qwen2.5-coder-3b-instruct-mlx")
    os.environ.setdefault("LMS_TIMEOUT_SECONDS", "1")
    bootstrap_config()
    yield


@pytest.fixture(scope="session", autouse=True)
def reset_database(bootstrap_environment: None) -> Iterator[None]:
    database = DataBase()
    storage_manager = StorageManager()
    sync_dsn = database.sync_engine_config.replace("+psycopg", "")
    admin_dsn = sync_dsn.rsplit("/", maxsplit=1)[0] + "/postgres"

    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database.db_name,),
            )
            cursor.execute(f'DROP DATABASE IF EXISTS "{database.db_name}"')
            cursor.execute(f'CREATE DATABASE "{database.db_name}"')

    storage_manager.get_valkey_sync().flushdb()

    if _has_alembic_revisions():
        alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_config.set_main_option(
            "script_location",
            str(BACKEND_DIR / "src/migrations"),
        )
        command.upgrade(alembic_config, "head")
        asyncio.run(_seed_reference_database())
    else:
        _create_schema(sync_engine_config=database.sync_engine_config)
        asyncio.run(_seed_reference_database())
    yield


@pytest_asyncio.fixture
async def storage_manager(reset_database: None) -> AsyncIterator[StorageManager]:
    manager = StorageManager()
    await manager.connect()
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def database(reset_database: None) -> AsyncIterator[DataBase]:
    database = DataBase()
    await database.init_alchemy_engine()
    yield database
    await database.dispose()


@pytest_asyncio.fixture(autouse=True)
async def prepare_test_state(storage_manager: StorageManager, database: DataBase) -> AsyncIterator[None]:
    storage_manager.get_valkey_sync().flushdb()

    await sync_reference_data(database)
    await load_reference_problem_bank(database)

    async with database.session_ctx() as session:
        await session.execute(delete(Course))
        await session.execute(delete(User).where(User.email != "admin@example.org"))

    await bootstrap_demo_course(storage_manager)

    yield


@pytest_asyncio.fixture
async def client(storage_manager: StorageManager) -> AsyncIterator[AsyncClient]:
    application = create_application(storage_manager)
    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest_asyncio.fixture
async def admin_tokens(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "email": "admin@example.org",
            "password": "Admin123!",
        },
    )
    assert response.status_code == 201
    tokens = TokenPairResponse.model_validate(response.json())
    return tokens.model_dump()


@pytest_asyncio.fixture
async def student_tokens(client: AsyncClient) -> dict[str, str]:
    unique_suffix = uuid.uuid4().hex
    email = f"student-{unique_suffix}@example.org"
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "first_name": "Student",
            "last_name": "User",
            "password": "Student123!",
            "avatar_url": None,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "Student123!",
        },
    )
    assert login_response.status_code == 201
    tokens = TokenPairResponse.model_validate(login_response.json())
    return tokens.model_dump()


def _has_alembic_revisions() -> bool:
    versions_dir = BACKEND_DIR / "src/migrations/versions"
    return any(versions_dir.glob("*.py"))


def _create_schema(sync_engine_config: str) -> None:
    engine = create_engine(sync_engine_config)

    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


async def _seed_reference_database() -> None:
    database = DataBase()
    await database.init_alchemy_engine()

    try:
        await sync_reference_data(database)
        await load_reference_problem_bank(database)
        async with database.session_ctx() as session:
            existing_admin = (
                await session.execute(
                    select(User).where(User.email == "admin@example.org")
                )
            ).scalar_one_or_none()
            if existing_admin is None:
                session.add(
                    User(
                        email="admin@example.org",
                        first_name="Admin",
                        last_name="User",
                        avatar_url=None,
                        hashed_password=hash_password("Admin123!"),
                        role=UserRole.ADMIN,
                        is_active=True,
                    )
                )
    finally:
        await database.dispose()
