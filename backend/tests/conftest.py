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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.core.utils import EnvTools, PasswordTools
from src.db.database import DataBase
from src.db.enums import ProblemAnswerOptionType, UserRole
from src.fast_api.fastapi_server import create_application
from src.models.alchemy import Base, Difficulty, Problem, ProblemAnswerOption, ProblemType, Subtopic, Topic, TopicSubtopic, User
from src.models.pydantic import TokenPairResponse
from src.valkey.valkey_client import get_valkey_client


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
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database.db_name,),
            )
            cursor.execute(f'DROP DATABASE IF EXISTS "{database.db_name}"')
            cursor.execute(
                f'CREATE DATABASE "{database.db_name}"'
            )

    get_valkey_client().flushdb()

    if _has_alembic_revisions():
        alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(BACKEND_DIR / "src/migrations"))
        command.upgrade(alembic_config, "head")
        _seed_database(database.sync_engine_config)
    else:
        _create_schema_and_seed(database.sync_engine_config)
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


def _has_alembic_revisions() -> bool:
    versions_dir = BACKEND_DIR / "src/migrations/versions"
    return any(versions_dir.glob("*.py"))


def _create_schema_and_seed(sync_engine_config: str) -> None:
    engine = create_engine(sync_engine_config)

    try:
        Base.metadata.create_all(engine)
        _seed_database(sync_engine_config)
    finally:
        engine.dispose()


def _seed_database(sync_engine_config: str) -> None:
    engine = create_engine(sync_engine_config)

    try:
        with Session(engine) as session:
            topic = Topic(name="Planimetry")
            subtopic = Subtopic(topic=topic, name="right triangle")
            untouched_subtopic = Subtopic(topic=topic, name="isosceles triangle")
            topic_link = TopicSubtopic(topic=topic, subtopic=subtopic, weight=1.0)
            untouched_topic_link = TopicSubtopic(topic=topic, subtopic=untouched_subtopic, weight=1.0)

            difficulty = Difficulty(name="medium", coefficient=1.5)
            problem_type = ProblemType(name="solve right-triangle configurations")

            problem = Problem(
                subtopic=subtopic,
                difficulty=difficulty,
                problem_type=problem_type,
                condition="In a right triangle, the legs are 6 and 8. Find the area.",
                solution="The area is 24.",
                condition_images=[],
                solution_images=[],
            )
            problem.answer_options = [
                ProblemAnswerOption(text="10", type=ProblemAnswerOptionType.WRONG),
                ProblemAnswerOption(text="24", type=ProblemAnswerOptionType.RIGHT),
                ProblemAnswerOption(text="I don't know", type=ProblemAnswerOptionType.I_DONT_KNOW),
            ]

            admin_user = User(
                email="admin@example.org",
                first_name="Admin",
                last_name="User",
                avatar_url=None,
                hashed_password=PasswordTools.hash_password("Admin123!"),
                role=UserRole.ADMIN,
                is_active=True,
            )

            session.add_all(
                [
                    topic,
                    topic_link,
                    untouched_subtopic,
                    untouched_topic_link,
                    difficulty,
                    problem_type,
                    problem,
                    admin_user,
                ]
            )
            session.commit()
    finally:
        engine.dispose()
