from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.db.database import DataBase
from src.db.models import ProblemAnswerOption

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


def build_auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def get_problem_ids_for_creation(client: AsyncClient) -> tuple[str, str, list[str]]:
    subtopics_response = await client.get("/subtopics")
    difficulties_response = await client.get("/difficulties")
    subskills_response = await client.get("/subskills")

    subtopics = subtopics_response.json()
    difficulties = difficulties_response.json()
    subskills = subskills_response.json()

    right_triangle_subtopic = next(item for item in subtopics if item["name"] == "right triangle")
    medium_difficulty = next(item for item in difficulties if item["name"] == "medium")
    needed_subskills = [
        item["id"]
        for item in subskills
        if item["name"] in {"solve right-triangle configurations", "compute lengths and areas in plane figures"}
    ]

    return right_triangle_subtopic["id"], medium_difficulty["id"], needed_subskills


async def get_problem_answer_ids(session: AsyncSession, problem_id: str) -> tuple[str, str]:
    result = await session.execute(
        select(ProblemAnswerOption).where(ProblemAnswerOption.problem_id == uuid.UUID(problem_id))
    )
    answer_options = result.scalars().all()
    correct_option = next(item for item in answer_options if item.is_correct)
    wrong_option = next(item for item in answer_options if not item.is_correct)
    return str(correct_option.id), str(wrong_option.id)


async def test_public_filters_accept_empty_uuid_values(client: AsyncClient) -> None:
    subtopics_response = await client.get("/subtopics?topic_id=")
    subskills_response = await client.get("/subskills?skill_id=")
    problems_response = await client.get("/problems?topic_id=")

    assert subtopics_response.status_code == 200
    assert subskills_response.status_code == 200
    assert problems_response.status_code == 200


async def test_public_problem_list_can_return_zero_results(client: AsyncClient) -> None:
    response = await client.get(f"/problems?topic_id={uuid.uuid4()}")

    assert response.status_code == 200
    assert response.json() == []


async def test_student_registration_login_and_profile(
    client: AsyncClient,
    student_tokens: dict[str, str],
) -> None:
    profile_response = await client.get(
        "/auth/me",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert profile_response.status_code == 200
    profile = profile_response.json()["user"]
    assert profile["role"] == "student"
    assert profile["email"].startswith("student-")


async def test_admin_routes_require_admin(
    client: AsyncClient,
    student_tokens: dict[str, str],
) -> None:
    response = await client.post(
        "/admin/topics",
        json={"name": f"Blocked {uuid.uuid4()}"},
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert response.status_code == 403


async def test_admin_problem_crud_and_public_shape(
    client: AsyncClient,
    admin_tokens: dict[str, str],
) -> None:
    subtopic_id, difficulty_id, subskill_ids = await get_problem_ids_for_creation(client)
    condition = f"Test condition {uuid.uuid4()}"

    create_response = await client.post(
        "/admin/problems",
        json={
            "subtopic_id": subtopic_id,
            "difficulty_id": difficulty_id,
            "condition": condition,
            "solution": "Test solution",
            "condition_images": [],
            "solution_images": [],
            "answer_options": [
                {"text": "10", "is_correct": False},
                {"text": "12", "is_correct": True},
                {"text": "14", "is_correct": False},
            ],
            "subskills": [
                {"subskill_id": subskill_ids[0], "weight": 0.6},
                {"subskill_id": subskill_ids[1], "weight": 0.4},
            ],
        },
        headers=build_auth_headers(admin_tokens["access_token"]),
    )

    assert create_response.status_code == 201
    created_problem = create_response.json()
    problem_id = created_problem["id"]
    assert all("subskill_id" in item and "weight" in item for item in created_problem["subskills"])
    assert all("is_correct" in item for item in created_problem["answer_options"])

    public_response = await client.get(f"/problems/{problem_id}")
    assert public_response.status_code == 200
    public_problem = public_response.json()
    assert public_problem["condition"] == condition
    assert "solution" not in public_problem
    assert all("is_correct" not in item for item in public_problem["answer_options"])

    update_response = await client.patch(
        f"/admin/problems/{problem_id}",
        json={"condition": f"{condition} updated"},
        headers=build_auth_headers(admin_tokens["access_token"]),
    )
    assert update_response.status_code == 200
    assert update_response.json()["condition"].endswith("updated")

    delete_response = await client.delete(
        f"/admin/problems/{problem_id}",
        headers=build_auth_headers(admin_tokens["access_token"]),
    )
    assert delete_response.status_code == 200

    missing_response = await client.get(f"/problems/{problem_id}")
    assert missing_response.status_code == 404


async def test_student_submission_updates_progress(
    client: AsyncClient,
    database: DataBase,
    student_tokens: dict[str, str],
) -> None:
    list_response = await client.get("/problems")
    assert list_response.status_code == 200
    problem_id = list_response.json()[0]["id"]

    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    async with database.async_session() as session:
        correct_answer_id, wrong_answer_id = await get_problem_answer_ids(session, problem_id)

    wrong_response = await client.post(
        f"/student/problems/{problem_id}/submit",
        json={"answer_option_id": wrong_answer_id},
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert wrong_response.status_code == 200
    assert wrong_response.json()["correct"] is False

    failed_progress = await client.get(
        "/student/progress",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert failed_progress.status_code == 200
    assert problem_id in failed_progress.json()["failed_problem_ids"]

    correct_response = await client.post(
        f"/student/problems/{problem_id}/submit",
        json={"answer_option_id": correct_answer_id},
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert correct_response.status_code == 200
    assert correct_response.json()["correct"] is True

    solved_progress = await client.get(
        "/student/progress",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert solved_progress.status_code == 200
    solved_payload = solved_progress.json()
    assert problem_id in solved_payload["solved_problem_ids"]
    assert problem_id not in solved_payload["failed_problem_ids"]
