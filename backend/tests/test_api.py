from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from src.models.alchemy import ProblemAnswerOption
from src.storage.db.enums import ProblemAnswerOptionType

if TYPE_CHECKING:
    from httpx import AsyncClient

    from src.storage.db.database import DataBase


def build_auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def create_course(
    client: AsyncClient,
    access_token: str,
    title: str,
) -> dict[str, Any]:
    response = await client.post(
        "/admin/courses",
        headers=build_auth_headers(access_token),
        json={"title": title, "description": f"{title} description"},
    )
    assert response.status_code == 201
    return dict(response.json())


async def fetch_problem_type_id(
    client: AsyncClient,
    access_token: str,
    problem_type_name: str,
) -> str:
    response = await client.get(
        "/problem-types",
        headers=build_auth_headers(access_token),
    )
    assert response.status_code == 200
    problem_type = next(
        item
        for item in response.json()
        if item["name"] == problem_type_name
    )
    return str(problem_type["id"])


async def create_course_node(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    name: str,
    problem_type_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/admin/courses/{course_id}/nodes",
        headers=build_auth_headers(access_token),
        json={
            "name": name,
            "description": f"{name} node",
            "problem_type_id": problem_type_id,
        },
    )
    assert response.status_code == 201
    return dict(response.json())


async def create_published_course(
    client: AsyncClient,
    access_token: str,
    title: str,
    problem_type_name: str = "compare and estimate real numbers",
) -> dict[str, Any]:
    course = await create_course(client, access_token, title)
    problem_type_id = await fetch_problem_type_id(
        client,
        access_token,
        problem_type_name,
    )
    course_node = await create_course_node(
        client,
        access_token,
        course["id"],
        problem_type_name,
        problem_type_id,
    )
    graph_version_response = await client.post(
        f"/admin/courses/{course['id']}/graph-versions",
        headers=build_auth_headers(access_token),
        json={"version_number": 1},
    )
    assert graph_version_response.status_code == 201
    graph_version = dict(graph_version_response.json())

    add_node_response = await client.post(
        f"/admin/courses/{course['id']}/graph-versions/{graph_version['id']}/nodes",
        headers=build_auth_headers(access_token),
        json={"course_node_id": course_node["id"], "lecture_id": None},
    )
    assert add_node_response.status_code == 201

    compile_response = await client.post(
        f"/admin/courses/{course['id']}/graph-versions/{graph_version['id']}/compile",
        headers=build_auth_headers(access_token),
    )
    assert compile_response.status_code == 200

    publish_response = await client.post(
        f"/admin/courses/{course['id']}/graph-versions/{graph_version['id']}/publish",
        headers=build_auth_headers(access_token),
    )
    assert publish_response.status_code == 200

    return course


async def enroll_student(
    client: AsyncClient,
    access_token: str,
    course_id: str,
) -> None:
    response = await client.post(
        f"/courses/{course_id}/enroll",
        headers=build_auth_headers(access_token),
    )
    assert response.status_code == 201


async def load_problem_answer_lookup(
    database: DataBase,
    problem_id: str,
) -> dict[ProblemAnswerOptionType, str]:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    async with database.async_session() as session:
        result = await session.execute(
            select(ProblemAnswerOption).where(
                ProblemAnswerOption.problem_id == uuid.UUID(problem_id)
            )
        )
        answer_options = result.scalars().all()

    return {
        answer_option.type: str(answer_option.id)
        for answer_option in answer_options
    }


async def complete_general_test(
    client: AsyncClient,
    database: DataBase,
    access_token: str,
    course_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/courses/{course_id}/tests/start",
        headers=build_auth_headers(access_token),
        json={"kind": "general"},
    )
    assert response.status_code == 200
    payload = dict(response.json())

    while True:
        problem = payload["problem"]
        if problem is None:
            raise AssertionError("Expected a problem before test completion")

        answer_lookup = await load_problem_answer_lookup(database, problem["id"])
        answer_response = await client.post(
            f"/tests/{payload['test_attempt']['id']}/answers",
            headers=build_auth_headers(access_token),
            json={
                "problem_id": problem["id"],
                "answer_option_id": answer_lookup[ProblemAnswerOptionType.RIGHT],
            },
        )
        assert answer_response.status_code == 201
        payload = dict(answer_response.json())
        if payload["graph_assessment"] is not None:
            return payload

        payload = {
            "test_attempt": payload["test_attempt"],
            "problem": payload["next_problem"],
            "graph_assessment": None,
        }


@pytest.mark.asyncio
async def test_auth_me_requires_authorization(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_registration_returns_plain_user_payload(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"user-{uuid.uuid4().hex}@example.org",
            "first_name": "Student",
            "last_name": "User",
            "password": "Student123!",
            "avatar_url": None,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"].endswith("@example.org")
    assert set(payload) == {
        "avatar_url",
        "email",
        "first_name",
        "id",
        "is_active",
        "last_name",
        "role",
    }


@pytest.mark.asyncio
async def test_active_courses_returns_enrolled_courses(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Active courses",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    response = await client.get(
        "/courses/active",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [course["id"]]


@pytest.mark.asyncio
async def test_entrance_kind_requires_absent_active_assessment(
    client: AsyncClient,
    database: DataBase,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Entrance kind restrictions",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])
    await complete_general_test(
        client,
        database,
        student_tokens["access_token"],
        course["id"],
    )

    response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={"kind": "entrance"},
    )

    assert response.status_code == 409
    assert "no active assessment" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pause_and_resume_test_reuses_same_attempt(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Pause resume",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    start_response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={"kind": "general"},
    )
    assert start_response.status_code == 200
    start_payload = start_response.json()
    assert start_payload["test_attempt"]["total_paused_seconds"] == 0

    await asyncio.sleep(1.1)

    pause_response = await client.post(
        f"/tests/{start_payload['test_attempt']['id']}/pause",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"
    paused_elapsed_seconds = pause_response.json()["elapsed_solve_seconds"]
    assert paused_elapsed_seconds >= 1

    await asyncio.sleep(1.1)

    resume_response = await client.post(
        f"/tests/{start_payload['test_attempt']['id']}/resume",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert resume_response.status_code == 200
    resume_payload = resume_response.json()
    assert resume_payload["test_attempt"]["id"] == start_payload["test_attempt"]["id"]
    assert resume_payload["test_attempt"]["status"] == "active"
    assert resume_payload["test_attempt"]["total_paused_seconds"] >= 1
    assert resume_payload["test_attempt"]["elapsed_solve_seconds"] <= paused_elapsed_seconds + 1
    assert resume_payload["problem"] is not None


@pytest.mark.asyncio
async def test_pause_resume_accumulates_total_paused_seconds_across_cycles(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Pause resume cycles",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    start_response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={"kind": "general"},
    )
    assert start_response.status_code == 200
    test_attempt_id = start_response.json()["test_attempt"]["id"]

    for _ in range(2):
        pause_response = await client.post(
            f"/tests/{test_attempt_id}/pause",
            headers=build_auth_headers(student_tokens["access_token"]),
        )
        assert pause_response.status_code == 200
        await asyncio.sleep(1.1)
        resume_response = await client.post(
            f"/tests/{test_attempt_id}/resume",
            headers=build_auth_headers(student_tokens["access_token"]),
        )
        assert resume_response.status_code == 200

    current_response = await client.get(
        f"/courses/{course['id']}/tests/current",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert current_response.status_code == 200
    assert current_response.json()["test_attempt"]["total_paused_seconds"] >= 2
