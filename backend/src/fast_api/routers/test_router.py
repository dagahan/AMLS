from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext
from src.models.pydantic.graph_assessment import GraphAssessmentResponse
from src.models.pydantic.test import (
    TestAnswerRequest,
    TestAnswerResponse,
    TestCurrentProblemResponse,
    TestAttemptResponse,
    TestStartRequest,
)
from src.services.graph_assessment import GraphAssessmentService
from src.services.test import TestService
from src.storage.db.enums import UserRole
from src.storage.storage_manager import StorageManager


def get_test_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["tests"])
    test_service = TestService(storage_manager)
    graph_assessment_service = GraphAssessmentService(storage_manager)


    @router.post(
        "/courses/{course_id}/tests/start",
        response_model=TestCurrentProblemResponse,
        status_code=200,
    )
    async def start_test(
        course_id: uuid.UUID,
        data: TestStartRequest,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> TestCurrentProblemResponse:
        return await test_service.start_test(auth.user.id, course_id, data)


    @router.get(
        "/courses/{course_id}/tests/current",
        response_model=TestCurrentProblemResponse,
        status_code=200,
    )
    async def get_current_test(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> TestCurrentProblemResponse:
        return await test_service.get_current_test(auth.user.id, course_id)


    @router.post("/tests/{test_attempt_id}/pause", response_model=TestAttemptResponse, status_code=200)
    async def pause_test(
        test_attempt_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> TestAttemptResponse:
        return await test_service.pause_test(auth.user.id, test_attempt_id)


    @router.post(
        "/tests/{test_attempt_id}/resume",
        response_model=TestCurrentProblemResponse,
        status_code=200,
    )
    async def resume_test(
        test_attempt_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> TestCurrentProblemResponse:
        return await test_service.resume_test(auth.user.id, test_attempt_id)


    @router.post(
        "/tests/{test_attempt_id}/answers",
        response_model=TestAnswerResponse,
        status_code=201,
    )
    async def submit_test_answer(
        test_attempt_id: uuid.UUID,
        data: TestAnswerRequest,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> TestAnswerResponse:
        return await test_service.submit_answer(auth.user.id, test_attempt_id, data)


    @router.get(
        "/courses/{course_id}/graph-assessments",
        response_model=list[GraphAssessmentResponse],
        status_code=200,
    )
    async def list_graph_assessments(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> list[GraphAssessmentResponse]:
        return await graph_assessment_service.list_course_assessments(auth.user.id, course_id)


    @router.get(
        "/courses/{course_id}/graph-assessments/active",
        response_model=GraphAssessmentResponse,
        status_code=200,
    )
    async def get_active_graph_assessment(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> GraphAssessmentResponse:
        return await graph_assessment_service.get_active_course_assessment(auth.user.id, course_id)


    return router
