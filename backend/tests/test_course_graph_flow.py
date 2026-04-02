from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from src.models.alchemy import (
    GraphAssessment as AssessmentRecord,
    ProblemAnswerOption,
    ResponseEvent,
    TestAttempt as AttemptRecord,
)
from src.storage.db.enums import ProblemAnswerOptionType, TestAttemptStatus as AttemptStatusEnum

if TYPE_CHECKING:
    from httpx import AsyncClient

    from src.storage.db.database import DataBase


def build_auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def fetch_problem_types(
    client: AsyncClient,
    access_token: str,
) -> list[dict[str, Any]]:
    response = await client.get("/problem-types", headers=build_auth_headers(access_token))
    assert response.status_code == 200
    return list(response.json())


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


async def create_course_node(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    name: str,
    problem_type_id: str | None,
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


async def create_graph_version(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    version_number: int,
) -> dict[str, Any]:
    response = await client.post(
        f"/admin/courses/{course_id}/graph-versions",
        headers=build_auth_headers(access_token),
        json={"version_number": version_number},
    )
    assert response.status_code == 201
    return dict(response.json())


async def add_graph_version_node(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    graph_version_id: str,
    course_node_id: str,
    lecture_id: str | None = None,
) -> dict[str, Any]:
    response = await client.post(
        f"/admin/courses/{course_id}/graph-versions/{graph_version_id}/nodes",
        headers=build_auth_headers(access_token),
        json={
            "course_node_id": course_node_id,
            "lecture_id": lecture_id,
        },
    )
    assert response.status_code == 201
    return dict(response.json())


async def add_graph_version_edge(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    graph_version_id: str,
    prerequisite_course_node_id: str,
    dependent_course_node_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/admin/courses/{course_id}/graph-versions/{graph_version_id}/edges",
        headers=build_auth_headers(access_token),
        json={
            "prerequisite_course_node_id": prerequisite_course_node_id,
            "dependent_course_node_id": dependent_course_node_id,
        },
    )
    assert response.status_code == 201
    return dict(response.json())


async def compile_graph_version(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    graph_version_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/admin/courses/{course_id}/graph-versions/{graph_version_id}/compile",
        headers=build_auth_headers(access_token),
    )
    assert response.status_code == 200
    return dict(response.json())


async def publish_graph_version(
    client: AsyncClient,
    access_token: str,
    course_id: str,
    graph_version_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/admin/courses/{course_id}/graph-versions/{graph_version_id}/publish",
        headers=build_auth_headers(access_token),
    )
    assert response.status_code == 200
    return dict(response.json())


async def enroll_student(
    client: AsyncClient,
    access_token: str,
    course_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/courses/{course_id}/enroll",
        headers=build_auth_headers(access_token),
    )
    assert response.status_code == 201
    return dict(response.json())


async def get_problem_answer_lookup(
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


async def create_published_course_with_nodes(
    client: AsyncClient,
    admin_access_token: str,
    title: str,
    problem_type_names: list[str],
    prerequisite_edges: list[tuple[int, int]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    problem_types = await fetch_problem_types(client, admin_access_token)
    problem_type_by_name = {
        problem_type["name"]: problem_type
        for problem_type in problem_types
    }
    course = await create_course(client, admin_access_token, title)
    course_nodes: list[dict[str, Any]] = []

    for problem_type_name in problem_type_names:
        problem_type = problem_type_by_name[problem_type_name]
        course_node = await create_course_node(
            client,
            admin_access_token,
            course["id"],
            problem_type_name,
            problem_type["id"],
        )
        course_nodes.append(course_node)

    graph_version = await create_graph_version(
        client,
        admin_access_token,
        course["id"],
        version_number=1,
    )
    for course_node in course_nodes:
        await add_graph_version_node(
            client,
            admin_access_token,
            course["id"],
            graph_version["id"],
            course_node["id"],
        )

    for from_index, to_index in prerequisite_edges:
        await add_graph_version_edge(
            client,
            admin_access_token,
            course["id"],
            graph_version["id"],
            course_nodes[from_index]["id"],
            course_nodes[to_index]["id"],
        )

    compile_payload = await compile_graph_version(
        client,
        admin_access_token,
        course["id"],
        graph_version["id"],
    )
    assert compile_payload["status"] == "ready"
    publish_payload = await publish_graph_version(
        client,
        admin_access_token,
        course["id"],
        graph_version["id"],
    )
    return course, course_nodes, publish_payload


async def complete_general_test(
    client: AsyncClient,
    database: DataBase,
    student_access_token: str,
    course_id: str,
) -> dict[str, Any]:
    response = await client.post(
        f"/courses/{course_id}/tests/start",
        headers=build_auth_headers(student_access_token),
        json={"kind": "general"},
    )
    assert response.status_code == 200
    payload = dict(response.json())

    while True:
        problem = payload["problem"]
        if problem is None:
            raise AssertionError("General test did not return a problem before completion")
        answer_lookup = await get_problem_answer_lookup(database, problem["id"])
        answer_response = await client.post(
            f"/tests/{payload['test_attempt']['id']}/answers",
            headers=build_auth_headers(student_access_token),
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

    return payload


@pytest.mark.asyncio
async def test_course_graph_compile_accepts_multi_parent_dag(
    client: AsyncClient,
    admin_tokens: dict[str, str],
) -> None:
    course, course_nodes, graph_version = await create_published_course_with_nodes(
        client=client,
        admin_access_token=admin_tokens["access_token"],
        title="Multi-parent DAG course",
        problem_type_names=[
            "compare and estimate real numbers",
            "compute with fractions and signed numbers",
            "convert fractions, decimals, and percentages",
        ],
        prerequisite_edges=[(0, 2), (1, 2)],
    )

    detail_response = await client.get(
        f"/courses/{course['id']}/graph-versions/{graph_version['id']}",
        headers=build_auth_headers(admin_tokens["access_token"]),
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()

    assert detail_payload["version"]["status"] == "ready"
    assert detail_payload["version"]["node_count"] == 3
    assert detail_payload["version"]["edge_count"] == 2
    assert len(detail_payload["nodes"]) == 3
    assert len(detail_payload["edges"]) == 2
    assert all(node["topological_rank"] is not None for node in detail_payload["nodes"])
    assert {node["course_node_id"] for node in detail_payload["nodes"]} == {
        course_node["id"]
        for course_node in course_nodes
    }


@pytest.mark.asyncio
async def test_lecture_pages_require_strict_sequence(
    client: AsyncClient,
    admin_tokens: dict[str, str],
) -> None:
    course = await create_course(client, admin_tokens["access_token"], "Lecture course")
    problem_types = await fetch_problem_types(client, admin_tokens["access_token"])
    problem_type = next(
        item
        for item in problem_types
        if item["name"] == "compare and estimate real numbers"
    )
    course_node = await create_course_node(
        client,
        admin_tokens["access_token"],
        course["id"],
        "lecture node",
        problem_type["id"],
    )

    lecture_response = await client.post(
        f"/admin/course-nodes/{course_node['id']}/lectures",
        headers=build_auth_headers(admin_tokens["access_token"]),
        json={"title": "Lecture 1"},
    )
    assert lecture_response.status_code == 201
    lecture = lecture_response.json()

    first_page_response = await client.post(
        f"/admin/lectures/{lecture['id']}/pages",
        headers=build_auth_headers(admin_tokens["access_token"]),
        json={"page_number": 1, "page_content": "x = 1"},
    )
    assert first_page_response.status_code == 201

    invalid_page_response = await client.post(
        f"/admin/lectures/{lecture['id']}/pages",
        headers=build_auth_headers(admin_tokens["access_token"]),
        json={"page_number": 3, "page_content": "x = 2"},
    )
    assert invalid_page_response.status_code == 409
    assert "must be 2" in invalid_page_response.json()["detail"]


@pytest.mark.asyncio
async def test_general_test_creates_active_graph_assessment_and_records_responses(
    client: AsyncClient,
    database: DataBase,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course, _, _ = await create_published_course_with_nodes(
        client=client,
        admin_access_token=admin_tokens["access_token"],
        title="Assessment course",
        problem_type_names=[
            "compare and estimate real numbers",
            "compute with fractions and signed numbers",
            "convert fractions, decimals, and percentages",
        ],
        prerequisite_edges=[(0, 1), (1, 2)],
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    completion_payload = await complete_general_test(
        client=client,
        database=database,
        student_access_token=student_tokens["access_token"],
        course_id=course["id"],
    )

    graph_assessment = completion_payload["graph_assessment"]
    assert graph_assessment is not None
    assert completion_payload["test_attempt"]["status"] == "completed"
    assert len(graph_assessment["state"]["learned_course_node_ids"]) == 3
    assert graph_assessment["is_active"] is True

    active_assessment_response = await client.get(
        f"/courses/{course['id']}/graph-assessments/active",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert active_assessment_response.status_code == 200
    active_assessment_payload = active_assessment_response.json()
    assert active_assessment_payload["id"] == graph_assessment["id"]

    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    async with database.async_session() as session:
        stored_responses = (
            await session.execute(
                select(ResponseEvent).where(
                    ResponseEvent.test_attempt_id
                    == uuid.UUID(completion_payload["test_attempt"]["id"])
                )
            )
        ).scalars().all()
        assert len(stored_responses) == 3
        assert all(response_event.course_node_id is not None for response_event in stored_responses)


@pytest.mark.asyncio
async def test_reset_course_deactivates_assessments_and_cancels_open_attempts(
    client: AsyncClient,
    database: DataBase,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course, _, _ = await create_published_course_with_nodes(
        client=client,
        admin_access_token=admin_tokens["access_token"],
        title="Reset course",
        problem_type_names=[
            "compare and estimate real numbers",
        ],
        prerequisite_edges=[],
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    await complete_general_test(
        client=client,
        database=database,
        student_access_token=student_tokens["access_token"],
        course_id=course["id"],
    )

    start_response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={"kind": "general"},
    )
    assert start_response.status_code == 200
    test_attempt = start_response.json()["test_attempt"]

    pause_response = await client.post(
        f"/tests/{test_attempt['id']}/pause",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert pause_response.status_code == 200

    reset_response = await client.post(
        f"/courses/{course['id']}/reset",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert reset_response.status_code == 200

    active_assessment_response = await client.get(
        f"/courses/{course['id']}/graph-assessments/active",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert active_assessment_response.status_code == 404

    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    async with database.async_session() as session:
        stored_test_attempt = await session.get(AttemptRecord, uuid.UUID(test_attempt["id"]))
        stored_graph_assessments = (
            await session.execute(select(AssessmentRecord))
        ).scalars().all()

    assert stored_test_attempt is not None
    assert stored_test_attempt.status == AttemptStatusEnum.CANCELLED
    assert any(graph_assessment.is_active is False for graph_assessment in stored_graph_assessments)
