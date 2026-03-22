from __future__ import annotations

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import (
    AuthContext,
    EntranceTestAnswerRequest,
    EntranceTestAnswerResponse,
    EntranceTestCurrentProblemResponse,
    EntranceTestResultResponse,
    EntranceTestSessionResponse,
    EntranceTestStructureCompileResponse,
)
from src.services.entrance_test import EntranceTestService
from src.storage.storage_manager import StorageManager
from src.storage.db.enums import UserRole


def get_entrance_test_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["entrance-test"])
    entrance_test_service = EntranceTestService(storage_manager)


    @router.post(
        "/admin/entrance-test/structure/compile",
        response_model=EntranceTestStructureCompileResponse,
        status_code=200,
    )
    async def compile_entrance_test_structure(
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> EntranceTestStructureCompileResponse:
        return await entrance_test_service.compile_current_structure()


    @router.get("/entrance-test", response_model=EntranceTestSessionResponse, status_code=200)
    async def get_entrance_test(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestSessionResponse:
        return await entrance_test_service.get_session(auth.user.id)


    @router.get(
        "/entrance-test/result",
        response_model=EntranceTestResultResponse,
        status_code=200,
    )
    async def get_entrance_test_result(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestResultResponse:
        return await entrance_test_service.get_result(auth.user.id)


    @router.post(
        "/entrance-test/start",
        response_model=EntranceTestCurrentProblemResponse,
        status_code=200,
    )
    async def start_entrance_test(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestCurrentProblemResponse:
        return await entrance_test_service.start_session(auth.user.id)


    @router.get(
        "/entrance-test/current-problem",
        response_model=EntranceTestCurrentProblemResponse,
        status_code=200,
    )
    async def get_current_entrance_test_problem(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestCurrentProblemResponse:
        return await entrance_test_service.get_current_problem(auth.user.id)


    @router.post(
        "/entrance-test/answers",
        response_model=EntranceTestAnswerResponse,
        status_code=201,
    )
    async def submit_entrance_test_answer(
        data: EntranceTestAnswerRequest,
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestAnswerResponse:
        return await entrance_test_service.submit_answer(auth.user.id, data)


    @router.post("/entrance-test/skip", response_model=EntranceTestSessionResponse, status_code=200)
    async def skip_entrance_test(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestSessionResponse:
        return await entrance_test_service.skip_session(auth.user.id)


    @router.post(
        "/entrance-test/complete",
        response_model=EntranceTestSessionResponse,
        status_code=200,
    )
    async def complete_entrance_test(
        auth: AuthContext = Depends(require_role(role=UserRole.STUDENT)),
    ) -> EntranceTestSessionResponse:
        return await entrance_test_service.complete_session(auth.user.id)


    return router
