from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
import sys
import uuid

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.core.clients import get_valkey_client
from src.core.utils import EnvTools
from src.db.database import DataBase
from src.fast_api.fastapi_server import create_application
from src.models.pydantic import TokenPairResponse


@pytest.fixture(scope="session", autouse=True)
def bootstrap_environment() -> Iterator[None]:
    EnvTools.bootstrap_env()
    yield


@pytest.fixture(scope="session", autouse=True)
def reset_database(bootstrap_environment: None) -> Iterator[None]:
    database = DataBase()
    sync_dsn = database.sync_engine_config.replace("+psycopg", "")
    admin_dsn = sync_dsn.rsplit("/", maxsplit=1)[0] + "/postgres"

    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (database.db_name,),
            )
            if cursor.fetchone() is None:
                cursor.execute(f'CREATE DATABASE "{database.db_name}"')

    with psycopg.connect(sync_dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cursor.execute("CREATE SCHEMA public")

    get_valkey_client().flushdb()

    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "src/migrations"))
    command.upgrade(alembic_config, "head")
    yield


@pytest_asyncio.fixture
async def database(reset_database: None) -> AsyncIterator[DataBase]:
    database = DataBase()
    await database.init_alchemy_engine()
    yield database
    await database.dispose()


@pytest_asyncio.fixture
async def client(database: DataBase) -> AsyncIterator[AsyncClient]:
    application = create_application(database)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
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
