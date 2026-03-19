from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING
from typing import cast

from sqlalchemy import select

from src.db.database import DataBase
from src.models.alchemy import Problem, ProblemAnswerOption
from src.s3.s3_connector import S3Client

if TYPE_CHECKING:
    from httpx import AsyncClient
    from pytest import MonkeyPatch
    from sqlalchemy.ext.asyncio import AsyncSession


def build_auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def build_mastery_map(items: list[dict[str, object]]) -> dict[str, float]:
    return {
        str(item["id"]): float(cast("float", item["mastery"]))
        for item in items
    }


async def get_problem_ids_for_creation(client: AsyncClient) -> tuple[str, str, list[str]]:
    subtopics_response = await client.get("/subtopics")
    difficulties_response = await client.get("/difficulties")
    skills_response = await client.get("/skills")

    subtopics = subtopics_response.json()
    difficulties = difficulties_response.json()
    skills = skills_response.json()

    right_triangle_subtopic = next(item for item in subtopics if item["name"] == "right triangle")
    medium_difficulty = next(item for item in difficulties if item["name"] == "medium")
    needed_skills = [
        item["id"]
        for item in skills
        if item["name"] in {"solve right-triangle configurations", "compute lengths and areas in plane figures"}
    ]

    return right_triangle_subtopic["id"], medium_difficulty["id"], needed_skills


async def get_problem_answer_ids(session: AsyncSession, problem_id: str) -> tuple[str, str]:
    problem_result = await session.execute(select(Problem).where(Problem.id == uuid.UUID(problem_id)))
    problem = problem_result.scalar_one()
    result = await session.execute(
        select(ProblemAnswerOption).where(ProblemAnswerOption.problem_id == uuid.UUID(problem_id))
    )
    answer_options = result.scalars().all()
    correct_option = next(item for item in answer_options if item.text == problem.right_answer)
    wrong_option = next(item for item in answer_options if item.text != problem.right_answer)
    return str(correct_option.id), str(wrong_option.id)


async def test_public_filters_accept_empty_uuid_values(client: AsyncClient) -> None:
    subtopics_response = await client.get("/subtopics?topic_id=")
    skills_response = await client.get("/skills")
    problems_response = await client.get("/problems?topic_id=")

    assert subtopics_response.status_code == 200
    assert skills_response.status_code == 200
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
    subtopic_id, difficulty_id, skill_ids = await get_problem_ids_for_creation(client)
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
            "answer_options": ["10", "12", "14"],
            "right_answer": "12",
            "skills": [
                {"skill_id": skill_ids[0], "weight": 0.6},
                {"skill_id": skill_ids[1], "weight": 0.4},
            ],
        },
        headers=build_auth_headers(admin_tokens["access_token"]),
    )

    assert create_response.status_code == 201
    created_problem = create_response.json()
    problem_id = created_problem["id"]
    assert all("skill_id" in item and "weight" in item for item in created_problem["skills"])
    assert created_problem["right_answer"] == "12"
    assert all("text" in item for item in created_problem["answer_options"])

    public_response = await client.get(f"/problems/{problem_id}")
    assert public_response.status_code == 200
    public_problem = public_response.json()
    assert public_problem["condition"] == condition
    assert "solution" not in public_problem
    assert "right_answer" not in public_problem

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


async def test_responses_and_mastery_endpoints(
    client: AsyncClient,
    database: DataBase,
    student_tokens: dict[str, str],
) -> None:
    list_response = await client.get("/problems")
    assert list_response.status_code == 200
    problem_payload = list_response.json()[0]
    problem_id = problem_payload["id"]
    subtopic_id = problem_payload["subtopic"]["id"]

    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    async with database.async_session() as session:
        correct_answer_id, wrong_answer_id = await get_problem_answer_ids(session, problem_id)

    overview_response = await client.get(
        "/mastery/overview",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert overview_response.status_code == 200
    initial_overview = overview_response.json()
    initial_skill_mastery = build_mastery_map(initial_overview["skills"])
    initial_subtopic_mastery = build_mastery_map(initial_overview["subtopics"])
    initial_topic_mastery = build_mastery_map(initial_overview["topics"])

    response_create = await client.post(
        "/responses",
        json={
            "problem_id": problem_id,
            "answer_option_id": wrong_answer_id,
        },
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert response_create.status_code == 201
    response_payload = response_create.json()
    assert response_payload["correct"] is False
    assert len(response_payload["skills"]) == 2
    assert len(response_payload["subtopics"]) == 1
    assert len(response_payload["topics"]) == 1

    updated_skill_mastery = build_mastery_map(response_payload["skills"])
    updated_subtopic_mastery = build_mastery_map(response_payload["subtopics"])
    updated_topic_mastery = build_mastery_map(response_payload["topics"])

    for mastery_value in updated_skill_mastery.values():
        assert mastery_value < 0.5
    for mastery_value in updated_subtopic_mastery.values():
        assert mastery_value < 0.5
    for mastery_value in updated_topic_mastery.values():
        assert mastery_value < 0.5

    first_skill_id = response_payload["skills"][0]["id"]
    first_topic_id = response_payload["topics"][0]["id"]

    skill_response = await client.get(
        f"/mastery/skills/{first_skill_id}",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    subtopic_response = await client.get(
        f"/mastery/subtopics/{subtopic_id}",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    topic_response = await client.get(
        f"/mastery/topics/{first_topic_id}",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert skill_response.status_code == 200
    assert subtopic_response.status_code == 200
    assert topic_response.status_code == 200

    follow_up_response = await client.post(
        "/responses",
        json={
            "problem_id": problem_id,
            "answer_option_id": correct_answer_id,
        },
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert follow_up_response.status_code == 201
    follow_up_payload = follow_up_response.json()
    assert follow_up_payload["correct"] is True

    final_overview_response = await client.get(
        "/mastery/overview",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert final_overview_response.status_code == 200
    final_overview = final_overview_response.json()
    final_skill_mastery = build_mastery_map(final_overview["skills"])
    final_subtopic_mastery = build_mastery_map(final_overview["subtopics"])
    final_topic_mastery = build_mastery_map(final_overview["topics"])

    for skill_id, mastery_value in updated_skill_mastery.items():
        assert initial_skill_mastery[skill_id] == 0.5
        assert abs(final_skill_mastery[skill_id] - 0.5) < 1e-6
        assert mastery_value != final_skill_mastery[skill_id]

    for current_subtopic_id, mastery_value in updated_subtopic_mastery.items():
        assert initial_subtopic_mastery[current_subtopic_id] == 0.5
        assert abs(final_subtopic_mastery[current_subtopic_id] - 0.5) < 1e-6
        assert mastery_value != final_subtopic_mastery[current_subtopic_id]

    for topic_id, mastery_value in updated_topic_mastery.items():
        assert initial_topic_mastery[topic_id] == 0.5
        assert abs(final_topic_mastery[topic_id] - 0.5) < 1e-6
        assert mastery_value != final_topic_mastery[topic_id]


async def test_storage_uploads_update_problem_and_profile_urls(
    client: AsyncClient,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
    monkeypatch: MonkeyPatch,
) -> None:
    os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
    os.environ.setdefault("S3_ENDPOINT_URL", "https://storage.example.org")
    os.environ.setdefault("S3_PUBLIC_BASE_URL", "https://storage.example.org/test-bucket")
    os.environ.setdefault("S3_ACCESS_KEY", "test-access")
    os.environ.setdefault("S3_SECRET_KEY", "test-secret")
    os.environ.setdefault("S3_REGION", "ru-7")
    os.environ.setdefault("S3_TLS_VERIFY", "1")

    async def fake_upload_bytes(
        self: S3Client,
        data: bytes,
        s3_key: str,
        content_type: str | None = None,
    ) -> None:
        return None


    async def fake_delete_object(self: S3Client, key: str) -> None:
        return None


    monkeypatch.setattr(S3Client, "upload_bytes", fake_upload_bytes)
    monkeypatch.setattr(S3Client, "delete_object", fake_delete_object)

    avatar_response = await client.post(
        "/storage/profile-image",
        headers=build_auth_headers(student_tokens["access_token"]),
        files={"file": ("avatar.png", b"avatar-bytes", "image/png")},
    )

    assert avatar_response.status_code == 201
    avatar_payload = avatar_response.json()
    assert avatar_payload["avatar_url"] is not None
    assert "/users/avatars/" in avatar_payload["avatar_url"]

    problem_image_response = await client.post(
        "/admin/problem-images/upload",
        headers=build_auth_headers(admin_tokens["access_token"]),
        data={"kind": "condition"},
        files=[("files", ("condition.png", b"condition-bytes", "image/png"))],
    )

    assert problem_image_response.status_code == 201
    uploaded_images = problem_image_response.json()
    assert len(uploaded_images) == 1
    assert "/problems/condition/" in uploaded_images[0]["url"]
