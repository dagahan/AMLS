from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.fast_api.dependencies import require_role
from src.models.pydantic import AuthContext
from src.models.pydantic.course import (
    CourseGraphVersionCreate,
    CourseGraphVersionDetailResponse,
    CourseGraphVersionEdgeCreate,
    CourseGraphVersionEdgeResponse,
    CourseGraphVersionNodeCreate,
    CourseGraphVersionNodeResponse,
    CourseGraphVersionResponse,
    CourseNodeCreate,
    CourseNodeResponse,
    CourseNodeUpdate,
)
from src.services.course_graph import CourseGraphService
from src.storage.db.enums import UserRole
from src.storage.storage_manager import StorageManager


def get_course_graph_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["course-graph"])
    course_graph_service = CourseGraphService(storage_manager)


    @router.get("/courses/{course_id}/nodes", response_model=list[CourseNodeResponse], status_code=200)
    async def list_course_nodes(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> list[CourseNodeResponse]:
        return await course_graph_service.list_course_nodes(course_id)


    @router.post("/admin/courses/{course_id}/nodes", response_model=CourseNodeResponse, status_code=201)
    async def create_course_node(
        course_id: uuid.UUID,
        data: CourseNodeCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseNodeResponse:
        return await course_graph_service.create_course_node(course_id, data)


    @router.patch(
        "/admin/courses/{course_id}/nodes/{course_node_id}",
        response_model=CourseNodeResponse,
        status_code=200,
    )
    async def update_course_node(
        course_id: uuid.UUID,
        course_node_id: uuid.UUID,
        data: CourseNodeUpdate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseNodeResponse:
        return await course_graph_service.update_course_node(course_id, course_node_id, data)


    @router.post(
        "/admin/courses/{course_id}/graph-versions",
        response_model=CourseGraphVersionResponse,
        status_code=201,
    )
    async def create_course_graph_version(
        course_id: uuid.UUID,
        data: CourseGraphVersionCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseGraphVersionResponse:
        return await course_graph_service.create_graph_version(course_id, data)


    @router.get(
        "/courses/{course_id}/graph-versions",
        response_model=list[CourseGraphVersionResponse],
        status_code=200,
    )
    async def list_course_graph_versions(
        course_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> list[CourseGraphVersionResponse]:
        return await course_graph_service.list_graph_versions(course_id)


    @router.get(
        "/courses/{course_id}/graph-versions/{graph_version_id}",
        response_model=CourseGraphVersionDetailResponse,
        status_code=200,
    )
    async def get_course_graph_version(
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        auth: AuthContext = Depends(require_role()),
    ) -> CourseGraphVersionDetailResponse:
        return await course_graph_service.get_graph_version_detail(course_id, graph_version_id)


    @router.post(
        "/admin/courses/{course_id}/graph-versions/{graph_version_id}/nodes",
        response_model=CourseGraphVersionNodeResponse,
        status_code=201,
    )
    async def add_course_graph_version_node(
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        data: CourseGraphVersionNodeCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseGraphVersionNodeResponse:
        return await course_graph_service.add_graph_version_node(course_id, graph_version_id, data)


    @router.post(
        "/admin/courses/{course_id}/graph-versions/{graph_version_id}/edges",
        response_model=CourseGraphVersionEdgeResponse,
        status_code=201,
    )
    async def add_course_graph_version_edge(
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        data: CourseGraphVersionEdgeCreate,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseGraphVersionEdgeResponse:
        return await course_graph_service.add_graph_version_edge(course_id, graph_version_id, data)


    @router.post(
        "/admin/courses/{course_id}/graph-versions/{graph_version_id}/compile",
        response_model=CourseGraphVersionResponse,
        status_code=200,
    )
    async def compile_course_graph_version(
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseGraphVersionResponse:
        return await course_graph_service.compile_graph_version(course_id, graph_version_id)


    @router.post(
        "/admin/courses/{course_id}/graph-versions/{graph_version_id}/publish",
        response_model=CourseGraphVersionResponse,
        status_code=200,
    )
    async def publish_course_graph_version(
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> CourseGraphVersionResponse:
        return await course_graph_service.publish_graph_version(course_id, graph_version_id)


    return router
