from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING
from typing import cast

from sqlalchemy import select

from src.db.database import DataBase
from src.models.alchemy import ProblemAnswerOption, ResponseEvent
from src.s3.s3_connector import S3Client
from src.valkey.mastery_cache import MasteryCache

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


def calculate_expected_mastery(success_sum: str, failure_sum: str) -> float:
    alpha = Decimal("2") + Decimal(success_sum)
    beta = Decimal("2") + Decimal(failure_sum)
    return float(alpha / (alpha + beta))


async def get_current_user_id(client: AsyncClient, access_token: str) -> str:
    response = await client.get(
        "/auth/me",
        headers=build_auth_headers(access_token),
    )
    assert response.status_code == 200
    return str(response.json()["user"]["id"])


async def get_problem_ids_for_creation(
    client: AsyncClient,
    access_token: str,
) -> tuple[str, str, str]:
    headers = build_auth_headers(access_token)
    subtopics_response = await client.get("/subtopics", headers=headers)
    difficulties_response = await client.get("/difficulties", headers=headers)
    problem_types_response = await client.get("/problem-types", headers=headers)

    subtopics = subtopics_response.json()
    difficulties = difficulties_response.json()
    problem_types = problem_types_response.json()

    right_triangle_subtopic = next(item for item in subtopics if item["name"] == "right triangle")
    medium_difficulty = next(item for item in difficulties if item["name"] == "medium")
    problem_type = next(
        item for item in problem_types if item["name"] == "solve right-triangle configurations"
    )

    return (
        right_triangle_subtopic["id"],
        medium_difficulty["id"],
        problem_type["id"],
    )


async def get_problem_answer_ids(session: AsyncSession, problem_id: str) -> tuple[str, str]:
    result = await session.execute(
        select(ProblemAnswerOption).where(ProblemAnswerOption.problem_id == uuid.UUID(problem_id))
    )
    answer_options = result.scalars().all()
    correct_option = next(item for item in answer_options if item.is_correct)
    wrong_option = next(item for item in answer_options if not item.is_correct)
    return str(correct_option.id), str(wrong_option.id)


async def test_protected_routes_require_authentication(client: AsyncClient) -> None:
    subtopics_response = await client.get("/subtopics?topic_id=")
    problem_types_response = await client.get("/problem-types")
    problems_response = await client.get("/problems?topic_id=")
    entrance_test_response = await client.get("/entrance-test")

    assert subtopics_response.status_code == 401
    assert problem_types_response.status_code == 401
    assert problems_response.status_code == 401
    assert entrance_test_response.status_code == 401


async def test_filters_accept_empty_uuid_values(
    client: AsyncClient,
    student_tokens: dict[str, str],
) -> None:
    headers = build_auth_headers(student_tokens["access_token"])
    subtopics_response = await client.get("/subtopics?topic_id=", headers=headers)
    problem_types_response = await client.get("/problem-types", headers=headers)
    problems_response = await client.get("/problems?topic_id=", headers=headers)

    assert subtopics_response.status_code == 200
    assert problem_types_response.status_code == 200
    assert problems_response.status_code == 200


async def test_problem_list_can_return_zero_results(
    client: AsyncClient,
    student_tokens: dict[str, str],
) -> None:
    response = await client.get(
        f"/problems?topic_id={uuid.uuid4()}",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

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
    assert profile["entrance_test"]["status"] == "pending"
    assert profile["entrance_test"]["answered_problems"] == 0
    assert profile["entrance_test"]["required"] is True


async def test_registration_creates_pending_entrance_test_session(client: AsyncClient) -> None:
    unique_suffix = uuid.uuid4().hex
    email = f"fresh-student-{unique_suffix}@example.org"

    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "first_name": "Fresh",
            "last_name": "Student",
            "password": "Student123!",
            "avatar_url": None,
        },
    )

    assert register_response.status_code == 201
    session_payload = register_response.json()["entrance_test"]
    assert session_payload["status"] == "pending"
    assert session_payload["total_problems"] == 1
    assert session_payload["answered_problems"] == 0
    assert session_payload["remaining_problems"] == 1
    assert session_payload["required"] is True


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


async def test_problem_type_graph_and_cycle_validation(
    client: AsyncClient,
    admin_tokens: dict[str, str],
) -> None:
    headers = build_auth_headers(admin_tokens["access_token"])

    base_response = await client.post(
        "/admin/problem-types",
        json={
            "name": f"base-{uuid.uuid4()}",
            "prerequisite_ids": [],
        },
        headers=headers,
    )
    assert base_response.status_code == 201
    base_problem_type = base_response.json()

    advanced_response = await client.post(
        "/admin/problem-types",
        json={
            "name": f"advanced-{uuid.uuid4()}",
            "prerequisite_ids": [base_problem_type["id"]],
        },
        headers=headers,
    )
    assert advanced_response.status_code == 201
    advanced_problem_type = advanced_response.json()

    graph_response = await client.get("/problem-types/graph", headers=headers)
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()

    base_node = next(
        item for item in graph_payload["roots"]
        if item["id"] == base_problem_type["id"]
    )
    assert base_node["children"][0]["id"] == advanced_problem_type["id"]

    cycle_response = await client.patch(
        f"/admin/problem-types/{base_problem_type['id']}",
        json={"prerequisite_ids": [advanced_problem_type["id"]]},
        headers=headers,
    )
    assert cycle_response.status_code == 422
    assert cycle_response.json()["detail"] == "Problem type prerequisites must not contain cycles"


async def test_admin_problem_crud_and_public_shape(
    client: AsyncClient,
    admin_tokens: dict[str, str],
) -> None:
    subtopic_id, difficulty_id, problem_type_id = await get_problem_ids_for_creation(
        client,
        admin_tokens["access_token"],
    )
    condition = f"Test condition {uuid.uuid4()}"

    create_response = await client.post(
        "/admin/problems",
        json={
            "subtopic_id": subtopic_id,
            "difficulty_id": difficulty_id,
            "problem_type_id": problem_type_id,
            "condition": condition,
            "solution": "Test solution",
            "condition_images": [],
            "solution_images": [],
            "answer_options": [
                {"text": "10", "is_correct": False},
                {"text": "12", "is_correct": True},
                {"text": "14", "is_correct": False},
            ],
        },
        headers=build_auth_headers(admin_tokens["access_token"]),
    )

    assert create_response.status_code == 201
    created_problem = create_response.json()
    problem_id = created_problem["id"]
    assert created_problem["problem_type"]["id"] == problem_type_id
    assert len([item for item in created_problem["answer_options"] if item["is_correct"]]) == 1
    assert all("text" in item and "is_correct" in item for item in created_problem["answer_options"])

    public_response = await client.get(
        f"/problems/{problem_id}",
        headers=build_auth_headers(admin_tokens["access_token"]),
    )
    assert public_response.status_code == 200
    public_problem = public_response.json()
    assert public_problem["condition"] == condition
    assert public_problem["problem_type"]["id"] == problem_type_id
    assert "solution" not in public_problem

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

    missing_response = await client.get(
        f"/problems/{problem_id}",
        headers=build_auth_headers(admin_tokens["access_token"]),
    )
    assert missing_response.status_code == 404


async def test_admin_problem_rejects_invalid_latex(
    client: AsyncClient,
    admin_tokens: dict[str, str],
) -> None:
    subtopic_id, difficulty_id, problem_type_id = await get_problem_ids_for_creation(
        client,
        admin_tokens["access_token"],
    )

    response = await client.post(
        "/admin/problems",
        json={
            "subtopic_id": subtopic_id,
            "difficulty_id": difficulty_id,
            "problem_type_id": problem_type_id,
            "condition": "\\frac{1}{",
            "solution": "x = 1",
            "condition_images": [],
            "solution_images": [],
            "answer_options": [
                {"text": "1", "is_correct": True},
                {"text": "2", "is_correct": False},
                {"text": "3", "is_correct": False},
            ],
        },
        headers=build_auth_headers(admin_tokens["access_token"]),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid LaTeX in condition: Missing close brace"


async def test_student_submission_updates_progress(
    client: AsyncClient,
    database: DataBase,
    student_tokens: dict[str, str],
) -> None:
    list_response = await client.get(
        "/problems",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
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
    list_response = await client.get(
        "/problems",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
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
    assert len(response_payload["subtopics"]) == 1
    assert len(response_payload["topics"]) == 1

    updated_subtopic_mastery = build_mastery_map(response_payload["subtopics"])
    updated_topic_mastery = build_mastery_map(response_payload["topics"])

    expected_wrong_subtopic_mastery = calculate_expected_mastery("0", "1.5")
    expected_wrong_topic_mastery = calculate_expected_mastery("0", "1.5")

    for mastery_value in updated_subtopic_mastery.values():
        assert abs(mastery_value - expected_wrong_subtopic_mastery) < 1e-6
    for mastery_value in updated_topic_mastery.values():
        assert abs(mastery_value - expected_wrong_topic_mastery) < 1e-6

    first_topic_id = response_payload["topics"][0]["id"]

    subtopic_response = await client.get(
        f"/mastery/subtopics/{subtopic_id}",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    topic_response = await client.get(
        f"/mastery/topics/{first_topic_id}",
        headers=build_auth_headers(student_tokens["access_token"]),
    )

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
    final_subtopic_mastery = build_mastery_map(final_overview["subtopics"])
    final_topic_mastery = build_mastery_map(final_overview["topics"])

    expected_correct_subtopic_mastery = calculate_expected_mastery("1.5", "0")
    expected_correct_topic_mastery = calculate_expected_mastery("1.5", "0")

    for current_subtopic_id, mastery_value in updated_subtopic_mastery.items():
        assert initial_subtopic_mastery[current_subtopic_id] == 0.5
        assert abs(final_subtopic_mastery[current_subtopic_id] - expected_correct_subtopic_mastery) < 1e-6
        assert mastery_value != final_subtopic_mastery[current_subtopic_id]

    for topic_id, mastery_value in updated_topic_mastery.items():
        assert initial_topic_mastery[topic_id] == 0.5
        assert abs(final_topic_mastery[topic_id] - expected_correct_topic_mastery) < 1e-6
        assert mastery_value != final_topic_mastery[topic_id]

    current_user_id = await get_current_user_id(client, student_tokens["access_token"])
    mastery_cache = MasteryCache()
    cached_overview = await mastery_cache.get_mastery_overview(current_user_id)
    assert cached_overview is not None

    cached_subtopic_values = sorted(float(item.mastery) for item in cached_overview.subtopics)
    cached_topic_values = sorted(float(item.mastery) for item in cached_overview.topics)
    assert cached_subtopic_values == sorted([expected_correct_subtopic_mastery, 0.5])
    assert cached_topic_values == [expected_correct_topic_mastery]

    touched_topic = cached_overview.topics[0]
    assert touched_topic.alpha == Decimal("3.5")
    assert touched_topic.beta == Decimal("2")


async def test_entrance_test_session_updates_mastery_and_progress(
    client: AsyncClient,
    database: DataBase,
    student_tokens: dict[str, str],
) -> None:
    session_response = await client.get(
        "/entrance-test",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert session_response.status_code == 200
    initial_session = session_response.json()
    problem_id = initial_session["current_problem_id"]
    assert initial_session["status"] == "pending"
    assert problem_id is not None

    start_response = await client.post(
        "/entrance-test/start",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert start_response.status_code == 200
    started_payload = start_response.json()
    assert started_payload["session"]["status"] == "active"
    assert started_payload["problem"]["id"] == problem_id

    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    current_user_id = await get_current_user_id(client, student_tokens["access_token"])

    async with database.async_session() as session:
        _, wrong_answer_id = await get_problem_answer_ids(session, problem_id)

    answer_response = await client.post(
        "/entrance-test/answers",
        json={
            "problem_id": problem_id,
            "answer_option_id": wrong_answer_id,
        },
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert answer_response.status_code == 201
    answer_payload = answer_response.json()
    assert answer_payload["response"]["correct"] is False
    assert answer_payload["session"]["status"] == "completed"
    assert answer_payload["session"]["answered_problems"] == 1
    assert answer_payload["session"]["required"] is False
    assert len(answer_payload["response"]["subtopics"]) == 1
    assert len(answer_payload["response"]["topics"]) == 1

    async with database.async_session() as session:
        result = await session.execute(
            select(ResponseEvent).where(
                ResponseEvent.problem_id == uuid.UUID(problem_id),
                ResponseEvent.user_id == uuid.UUID(current_user_id),
            )
        )
        stored_responses = result.scalars().all()
        assert len(stored_responses) == 1

    current_problem_response = await client.get(
        "/entrance-test/current-problem",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert current_problem_response.status_code == 200
    assert current_problem_response.json()["problem"] is None

    progress_response = await client.get(
        "/student/progress",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert progress_response.status_code == 200
    assert problem_id in progress_response.json()["failed_problem_ids"]


async def test_entrance_test_can_be_skipped(
    client: AsyncClient,
) -> None:
    unique_suffix = uuid.uuid4().hex
    email = f"skip-student-{unique_suffix}@example.org"

    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "first_name": "Skip",
            "last_name": "Student",
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
    access_token = login_response.json()["access_token"]

    skip_response = await client.post(
        "/entrance-test/skip",
        headers=build_auth_headers(access_token),
    )
    assert skip_response.status_code == 200
    skipped_session = skip_response.json()
    assert skipped_session["status"] == "skipped"
    assert skipped_session["required"] is False

    start_response = await client.post(
        "/entrance-test/start",
        headers=build_auth_headers(access_token),
    )
    assert start_response.status_code == 409
    assert start_response.json()["detail"] == "Entrance test has already been skipped"


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
