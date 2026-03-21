from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.db.database import DataBase
from src.db.enums import ProblemAnswerOptionType
from src.models.alchemy import ProblemAnswerOption, ResponseEvent
from src.s3.s3_connector import S3Client

if TYPE_CHECKING:
    from httpx import AsyncClient
    from pytest import MonkeyPatch
    from sqlalchemy.ext.asyncio import AsyncSession


def build_auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


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
    correct_option = next(
        item for item in answer_options
        if item.type == ProblemAnswerOptionType.RIGHT
    )
    wrong_option = next(
        item for item in answer_options
        if item.type == ProblemAnswerOptionType.WRONG
    )
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
    assert profile["entrance_test"]["structure_version"] == 1
    assert profile["entrance_test"]["current_problem_id"] is None


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
    assert session_payload["structure_version"] == 1
    assert session_payload["current_problem_id"] is None


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
                {"text": "10", "type": "wrong"},
                {"text": "12", "type": "right"},
                {"text": "I don't know", "type": "i_dont_know"},
            ],
        },
        headers=build_auth_headers(admin_tokens["access_token"]),
    )

    assert create_response.status_code == 201
    created_problem = create_response.json()
    problem_id = created_problem["id"]
    assert created_problem["problem_type"]["id"] == problem_type_id
    assert len([item for item in created_problem["answer_options"] if item["type"] == "right"]) == 1
    assert len([item for item in created_problem["answer_options"] if item["type"] == "i_dont_know"]) == 1
    assert all("text" in item and "type" in item for item in created_problem["answer_options"])

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
                {"text": "1", "type": "right"},
                {"text": "2", "type": "wrong"},
                {"text": "I don't know", "type": "i_dont_know"},
            ],
        },
        headers=build_auth_headers(admin_tokens["access_token"]),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid LaTeX in condition: Missing close brace"


async def test_removed_old_practice_and_intelligence_routes(
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
        _, wrong_answer_id = await get_problem_answer_ids(session, problem_id)

    progress_response = await client.get(
        "/student/progress",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    submit_response = await client.post(
        f"/student/problems/{problem_id}/submit",
        json={"answer_option_id": wrong_answer_id},
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    removed_overview_response = await client.get(
        "/mastery/overview",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    raw_response_endpoint = await client.post(
        "/responses",
        json={
            "problem_id": problem_id,
            "answer_option_id": wrong_answer_id,
        },
        headers=build_auth_headers(student_tokens["access_token"]),
    )

    assert progress_response.status_code == 404
    assert submit_response.status_code == 404
    assert removed_overview_response.status_code == 404
    assert raw_response_endpoint.status_code == 404


async def test_entrance_test_session_records_raw_response(
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
    assert initial_session["status"] == "pending"
    assert initial_session["current_problem_id"] is None

    start_response = await client.post(
        "/entrance-test/start",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert start_response.status_code == 200
    started_payload = start_response.json()
    problem_id = started_payload["session"]["current_problem_id"]
    assert started_payload["session"]["status"] == "active"
    assert problem_id is not None
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
    assert answer_payload["response"]["answer_option_type"] == "wrong"
    assert answer_payload["session"]["status"] == "completed"
    assert answer_payload["session"]["current_problem_id"] is None

    async with database.async_session() as session:
        result = await session.execute(
            select(ResponseEvent).where(
                ResponseEvent.problem_id == uuid.UUID(problem_id),
                ResponseEvent.user_id == uuid.UUID(current_user_id),
            )
        )
        stored_responses = result.scalars().all()
        assert len(stored_responses) == 1
        assert stored_responses[0].answer_option_id == uuid.UUID(wrong_answer_id)
        assert stored_responses[0].entrance_test_session_id == uuid.UUID(answer_payload["session"]["id"])

    current_problem_response = await client.get(
        "/entrance-test/current-problem",
        headers=build_auth_headers(student_tokens["access_token"]),
    )
    assert current_problem_response.status_code == 200
    assert current_problem_response.json()["problem"] is None


async def test_entrance_assessment_advances_to_dependent_problem_type(
    client: AsyncClient,
    database: DataBase,
    admin_tokens: dict[str, str],
    student_tokens: dict[str, str],
) -> None:
    admin_headers = build_auth_headers(admin_tokens["access_token"])
    student_headers = build_auth_headers(student_tokens["access_token"])
    subtopic_id, difficulty_id, root_problem_type_id = await get_problem_ids_for_creation(
        client,
        admin_tokens["access_token"],
    )

    child_problem_type_response = await client.post(
        "/admin/problem-types",
        json={
            "name": f"adaptive-child-{uuid.uuid4()}",
            "prerequisite_ids": [root_problem_type_id],
        },
        headers=admin_headers,
    )
    assert child_problem_type_response.status_code == 201
    child_problem_type_id = child_problem_type_response.json()["id"]

    child_problem_response = await client.post(
        "/admin/problems",
        json={
            "subtopic_id": subtopic_id,
            "difficulty_id": difficulty_id,
            "problem_type_id": child_problem_type_id,
            "condition": "Find the length of the hypotenuse when the legs are 5 and 12.",
            "solution": "The hypotenuse is 13.",
            "condition_images": [],
            "solution_images": [],
            "answer_options": [
                {"text": "13", "type": "right"},
                {"text": "12", "type": "wrong"},
                {"text": "I don't know", "type": "i_dont_know"},
            ],
        },
        headers=admin_headers,
    )
    assert child_problem_response.status_code == 201
    child_problem_id = child_problem_response.json()["id"]

    start_response = await client.post("/entrance-test/start", headers=student_headers)
    assert start_response.status_code == 200
    started_payload = start_response.json()
    first_problem_id = started_payload["session"]["current_problem_id"]
    assert first_problem_id is not None
    first_problem_type_id = started_payload["problem"]["problem_type"]["id"]
    assert first_problem_type_id in {root_problem_type_id, child_problem_type_id}

    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    async with database.async_session() as session:
        first_right_answer_id, _ = await get_problem_answer_ids(session, first_problem_id)

    first_answer_response = await client.post(
        "/entrance-test/answers",
        json={
            "problem_id": first_problem_id,
            "answer_option_id": first_right_answer_id,
        },
        headers=student_headers,
    )
    assert first_answer_response.status_code == 201
    first_answer_payload = first_answer_response.json()
    assert first_answer_payload["response"]["answer_option_type"] == "right"
    assert first_answer_payload["session"]["status"] == "active"

    second_problem_id = first_answer_payload["session"]["current_problem_id"]
    assert second_problem_id is not None
    assert second_problem_id != first_problem_id

    current_problem_response = await client.get(
        "/entrance-test/current-problem",
        headers=student_headers,
    )
    assert current_problem_response.status_code == 200
    current_problem_payload = current_problem_response.json()
    assert current_problem_payload["problem"]["id"] == second_problem_id

    second_problem_type_id = current_problem_payload["problem"]["problem_type"]["id"]
    assert {first_problem_type_id, second_problem_type_id} == {
        root_problem_type_id,
        child_problem_type_id,
    }

    async with database.async_session() as session:
        second_right_answer_id, _ = await get_problem_answer_ids(session, second_problem_id)

    second_answer_response = await client.post(
        "/entrance-test/answers",
        json={
            "problem_id": second_problem_id,
            "answer_option_id": second_right_answer_id,
        },
        headers=student_headers,
    )
    assert second_answer_response.status_code == 201
    second_answer_payload = second_answer_response.json()
    assert second_answer_payload["response"]["answer_option_type"] == "right"
    assert second_answer_payload["session"]["status"] == "completed"
    assert second_answer_payload["session"]["current_problem_id"] is None

    current_user_id = await get_current_user_id(client, student_tokens["access_token"])

    async with database.async_session() as session:
        result = await session.execute(
            select(ResponseEvent).where(
                ResponseEvent.user_id == uuid.UUID(current_user_id),
            )
        )
        stored_responses = result.scalars().all()
        assert len(stored_responses) == 2
        assert {response.problem_id for response in stored_responses} == {
            uuid.UUID(first_problem_id),
            uuid.UUID(second_problem_id),
        }


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
    assert skipped_session["current_problem_id"] is None

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
