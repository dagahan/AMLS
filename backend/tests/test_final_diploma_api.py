from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models.alchemy import Course, CourseNode, Lecture, ProblemAnswerOption
from src.services.graph_assessment.review_generation_service import (
    GeneratedAssessmentReview,
    GraphAssessmentReviewService,
)
from src.storage.db.enums import GraphAssessmentReviewStatus
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


async def complete_test_with_right_answers(
    client: AsyncClient,
    database: DataBase,
    access_token: str,
    course_id: str,
    kind: str,
) -> dict[str, Any]:
    start_response = await client.post(
        f"/courses/{course_id}/tests/start",
        headers=build_auth_headers(access_token),
        json={"kind": kind},
    )
    assert start_response.status_code == 200
    payload = dict(start_response.json())

    for _ in range(24):
        problem = payload["problem"]
        if problem is None:
            return payload

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
        next_payload = dict(answer_response.json())
        if next_payload["graph_assessment"] is not None:
            return {
                "test_attempt": next_payload["test_attempt"],
                "problem": None,
                "graph_assessment": next_payload["graph_assessment"],
            }

        if next_payload["next_problem"] is None:
            return {
                "test_attempt": next_payload["test_attempt"],
                "problem": None,
                "graph_assessment": None,
            }

        payload = {
            "test_attempt": next_payload["test_attempt"],
            "problem": next_payload["next_problem"],
            "graph_assessment": None,
        }

    raise AssertionError("Test completion did not finish within expected question count")


@pytest.mark.asyncio
async def test_profile_patch_updates_student_name(
    client: AsyncClient,
    student_tokens: dict[str, str],
) -> None:
    patch_response = await client.patch(
        "/users/me",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={
            "first_name": "Updated",
            "last_name": "Student",
        },
    )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["first_name"] == "Updated"
    assert payload["last_name"] == "Student"

    me_response = await client.get(
        "/auth/me",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert me_response.status_code == 200
    assert me_response.json()["user"]["first_name"] == "Updated"
    assert me_response.json()["user"]["last_name"] == "Student"


@pytest.mark.asyncio
async def test_workspace_endpoint_returns_graph_and_flags(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Workspace payload",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    response = await client.get(
        f"/courses/{course['id']}/workspace",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["course"]["id"] == course["id"]
    assert len(payload["nodes"]) == 1
    assert len(payload["edges"]) == 0
    assert payload["action_flags"]["can_start_entrance"] is True
    assert payload["action_flags"]["can_start_practice"] is True


@pytest.mark.asyncio
async def test_exam_completion_does_not_create_graph_assessment(
    client: AsyncClient,
    database: DataBase,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Exam no writeback",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    completion_payload = await complete_test_with_right_answers(
        client=client,
        database=database,
        access_token=student_tokens["access_token"],
        course_id=course["id"],
        kind="exam",
    )

    assert completion_payload["graph_assessment"] is None

    assessments_response = await client.get(
        f"/courses/{course['id']}/graph-assessments",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert assessments_response.status_code == 200
    assert assessments_response.json() == []


@pytest.mark.asyncio
async def test_reveal_solution_is_recorded_in_attempt_review(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Reveal marker",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    start_response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={"kind": "general"},
    )
    assert start_response.status_code == 200
    start_payload = start_response.json()

    reveal_response = await client.post(
        f"/tests/{start_payload['test_attempt']['id']}/reveal-solution",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert reveal_response.status_code == 200
    reveal_payload = reveal_response.json()
    assert reveal_payload["response"]["revealed_solution"] is True

    review_response = await client.get(
        f"/tests/{start_payload['test_attempt']['id']}/review",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert len(review_payload["items"]) >= 1
    assert review_payload["items"][0]["revealed_solution"] is True
    assert review_payload["items"][0]["chosen_answer_option_type"] in {"wrong", "i_dont_know"}


@pytest.mark.asyncio
async def test_unenroll_cancels_open_attempts_and_preserves_history(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Unenroll cancellation",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    start_response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={"kind": "general"},
    )
    assert start_response.status_code == 200
    test_attempt_id = start_response.json()["test_attempt"]["id"]

    unenroll_response = await client.post(
        f"/courses/{course['id']}/unenroll",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert unenroll_response.status_code == 200
    assert unenroll_response.json()["is_active"] is False

    history_response = await client.get(
        f"/courses/{course['id']}/tests/history",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert history_response.status_code == 200
    history_payload = history_response.json()

    attempt_record = next(
        item
        for item in history_payload["attempts"]
        if item["id"] == test_attempt_id
    )
    assert attempt_record["status"] == "cancelled"


@pytest.mark.asyncio
async def test_reenroll_after_unenroll_reactivates_enrollment_without_server_error(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Reenroll lifecycle",
    )

    first_enroll_response = await client.post(
        f"/courses/{course['id']}/enroll",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert first_enroll_response.status_code == 201
    assert first_enroll_response.json()["is_active"] is True

    unenroll_response = await client.post(
        f"/courses/{course['id']}/unenroll",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert unenroll_response.status_code == 200
    assert unenroll_response.json()["is_active"] is False

    second_enroll_response = await client.post(
        f"/courses/{course['id']}/enroll",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert second_enroll_response.status_code == 201
    assert second_enroll_response.json()["is_active"] is True

    active_courses_response = await client.get(
        "/courses/active",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert active_courses_response.status_code == 200
    active_course_ids = {
        item["id"]
        for item in active_courses_response.json()
    }
    assert course["id"] in active_course_ids


@pytest.mark.asyncio
async def test_single_node_custom_selection_supports_completion_and_perfect_confidence(
    client: AsyncClient,
    database: DataBase,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    course = await create_published_course(
        client,
        admin_tokens["access_token"],
        "Single node custom selection",
    )
    await enroll_student(client, student_tokens["access_token"], course["id"])

    workspace_response = await client.get(
        f"/courses/{course['id']}/workspace",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    target_node_id = workspace_payload["nodes"][0]["course_node_id"]

    start_response = await client.post(
        f"/courses/{course['id']}/tests/start",
        headers=build_auth_headers(student_tokens["access_token"]),
        json={
            "kind": "general",
            "target_course_node_ids": [target_node_id],
        },
    )
    assert start_response.status_code == 200
    payload = start_response.json()

    asked_problem_ids: list[str] = []
    for question_index in range(8):
        current_problem = payload["problem"]
        assert current_problem is not None
        asked_problem_ids.append(current_problem["id"])
        answer_lookup = await load_problem_answer_lookup(database, current_problem["id"])
        answer_response = await client.post(
            f"/tests/{payload['test_attempt']['id']}/answers",
            headers=build_auth_headers(student_tokens["access_token"]),
            json={
                "problem_id": current_problem["id"],
                "answer_option_id": answer_lookup[ProblemAnswerOptionType.RIGHT],
            },
        )
        assert answer_response.status_code == 201
        answer_payload = answer_response.json()

        if answer_payload["graph_assessment"] is not None:
            assert answer_payload["graph_assessment"]["state_confidence"] == 1.0
            break

        payload = {
            "test_attempt": answer_payload["test_attempt"],
            "problem": answer_payload["next_problem"],
        }
    else:
        raise AssertionError("Single-node custom selection did not complete in expected range")

    assert len(asked_problem_ids) >= 1
    assert len(set(asked_problem_ids)) >= 1


@pytest.mark.asyncio
async def test_demo_bootstrap_persists_course_node_descriptions_and_unique_lecture_pages(
    database: DataBase,
) -> None:
    async with database.session_ctx() as session:
        course_result = await session.execute(
            select(Course).where(Course.title == "Profile Mathematics (Grades 10-11)")
        )
        course = course_result.scalar_one_or_none()
        assert course is not None
        assert course.description is not None
        assert course.description.count(".") >= 4

        nodes_result = await session.execute(
            select(CourseNode)
            .options(selectinload(CourseNode.lectures).selectinload(Lecture.pages))
            .where(CourseNode.course_id == course.id)
        )
        course_nodes = list(nodes_result.scalars().all())
        assert len(course_nodes) == 94

        first_page_contents: list[str] = []
        for course_node in course_nodes:
            assert course_node.description is not None
            assert "This node develops the skill to" in course_node.description
            assert len(course_node.lectures) >= 1
            lecture = course_node.lectures[0]
            lecture_pages = sorted(
                list(lecture.pages),
                key=lambda page: (page.page_number, str(page.id)),
            )
            assert len(lecture_pages) == 4
            assert course_node.name in lecture_pages[0].page_content
            first_page_contents.append(lecture_pages[0].page_content)

        assert len(set(first_page_contents)) == len(first_page_contents)
