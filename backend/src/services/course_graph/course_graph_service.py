from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.logging import get_logger
from src.models.alchemy import (
    Course,
    CourseGraphVersion,
    CourseGraphVersionEdge,
    CourseGraphVersionNode,
    CourseNode,
    Lecture,
)
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
from src.services.problem.loader import ensure_problem_type_exists
from src.storage.db.enums import CourseGraphVersionStatus
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class CourseGraphService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def list_course_nodes(self, course_id: uuid.UUID) -> list[CourseNodeResponse]:
        async with self.storage_manager.session_ctx() as session:
            await self._load_course_or_404(session, course_id)
            result = await session.execute(
                select(CourseNode)
                .where(CourseNode.course_id == course_id)
                .order_by(CourseNode.created_at, CourseNode.id)
            )
            course_nodes = result.scalars().all()
            return [CourseNodeResponse.model_validate(course_node) for course_node in course_nodes]


    async def create_course_node(
        self,
        course_id: uuid.UUID,
        data: CourseNodeCreate,
    ) -> CourseNodeResponse:
        async with self.storage_manager.session_ctx() as session:
            await self._load_course_or_404(session, course_id)
            if data.problem_type_id is not None:
                await ensure_problem_type_exists(session, data.problem_type_id)

            course_node = CourseNode(
                course_id=course_id,
                problem_type_id=data.problem_type_id,
                name=data.name,
                description=data.description,
            )
            session.add(course_node)
            await session.flush()
            logger.info(
                "Created course node: course_node_id={}, course_id={}, problem_type_id={}",
                course_node.id,
                course_id,
                course_node.problem_type_id,
            )
            return CourseNodeResponse.model_validate(course_node)


    async def update_course_node(
        self,
        course_id: uuid.UUID,
        course_node_id: uuid.UUID,
        data: CourseNodeUpdate,
    ) -> CourseNodeResponse:
        async with self.storage_manager.session_ctx() as session:
            course_node = await self._load_course_node_or_404(session, course_id, course_node_id)
            if data.problem_type_id is not None:
                await ensure_problem_type_exists(session, data.problem_type_id)
                course_node.problem_type_id = data.problem_type_id
            if data.name is not None:
                course_node.name = data.name
            if data.description is not None:
                course_node.description = data.description

            await session.flush()
            logger.info(
                "Updated course node: course_node_id={}, course_id={}",
                course_node_id,
                course_id,
            )
            return CourseNodeResponse.model_validate(course_node)


    async def create_graph_version(
        self,
        course_id: uuid.UUID,
        data: CourseGraphVersionCreate,
    ) -> CourseGraphVersionResponse:
        async with self.storage_manager.session_ctx() as session:
            await self._load_course_or_404(session, course_id)
            graph_version = CourseGraphVersion(
                course_id=course_id,
                version_number=data.version_number,
                status=CourseGraphVersionStatus.DRAFT,
                node_count=0,
                edge_count=0,
                built_at=None,
                error_message=None,
            )
            session.add(graph_version)
            await session.flush()
            logger.info(
                "Created course graph version: graph_version_id={}, course_id={}, version_number={}",
                graph_version.id,
                course_id,
                data.version_number,
            )
            return CourseGraphVersionResponse.model_validate(graph_version)


    async def list_graph_versions(self, course_id: uuid.UUID) -> list[CourseGraphVersionResponse]:
        async with self.storage_manager.session_ctx() as session:
            await self._load_course_or_404(session, course_id)
            result = await session.execute(
                select(CourseGraphVersion)
                .where(CourseGraphVersion.course_id == course_id)
                .order_by(CourseGraphVersion.version_number.desc())
            )
            graph_versions = result.scalars().all()
            return [
                CourseGraphVersionResponse.model_validate(graph_version)
                for graph_version in graph_versions
            ]


    async def get_graph_version_detail(
        self,
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
    ) -> CourseGraphVersionDetailResponse:
        async with self.storage_manager.session_ctx() as session:
            graph_version = await self._load_graph_version_or_404(
                session,
                course_id,
                graph_version_id,
            )
            return self._build_graph_version_detail_response(graph_version)


    async def add_graph_version_node(
        self,
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        data: CourseGraphVersionNodeCreate,
    ) -> CourseGraphVersionNodeResponse:
        async with self.storage_manager.session_ctx() as session:
            graph_version = await self._load_graph_version_or_404(
                session,
                course_id,
                graph_version_id,
            )
            self._ensure_mutable_graph_version(graph_version)
            await self._load_course_node_or_404(session, course_id, data.course_node_id)
            await self._validate_lecture_binding(
                session=session,
                course_node_id=data.course_node_id,
                lecture_id=data.lecture_id,
            )

            graph_version_node = CourseGraphVersionNode(
                graph_version_id=graph_version_id,
                course_node_id=data.course_node_id,
                lecture_id=data.lecture_id,
                topological_rank=None,
            )
            session.add(graph_version_node)
            await session.flush()
            logger.info(
                "Added course graph version node: graph_version_node_id={}, graph_version_id={}, course_node_id={}, lecture_id={}",
                graph_version_node.id,
                graph_version_id,
                data.course_node_id,
                data.lecture_id,
            )
            return CourseGraphVersionNodeResponse.model_validate(graph_version_node)


    async def add_graph_version_edge(
        self,
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
        data: CourseGraphVersionEdgeCreate,
    ) -> CourseGraphVersionEdgeResponse:
        async with self.storage_manager.session_ctx() as session:
            graph_version = await self._load_graph_version_or_404(
                session,
                course_id,
                graph_version_id,
            )
            self._ensure_mutable_graph_version(graph_version)
            version_membership = await self._load_graph_version_membership(session, graph_version_id)
            if data.prerequisite_course_node_id not in version_membership:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Prerequisite course node is not present in this graph version",
                )
            if data.dependent_course_node_id not in version_membership:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Dependent course node is not present in this graph version",
                )

            graph_version_edge = CourseGraphVersionEdge(
                graph_version_id=graph_version_id,
                prerequisite_course_node_id=data.prerequisite_course_node_id,
                dependent_course_node_id=data.dependent_course_node_id,
            )
            session.add(graph_version_edge)
            await session.flush()
            logger.info(
                "Added course graph version edge: graph_version_edge_id={}, graph_version_id={}, prerequisite_course_node_id={}, dependent_course_node_id={}",
                graph_version_edge.id,
                graph_version_id,
                data.prerequisite_course_node_id,
                data.dependent_course_node_id,
            )
            return CourseGraphVersionEdgeResponse.model_validate(graph_version_edge)


    async def compile_graph_version(
        self,
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
    ) -> CourseGraphVersionResponse:
        async with self.storage_manager.session_ctx() as session:
            graph_version = await self._load_graph_version_or_404(
                session,
                course_id,
                graph_version_id,
            )
            self._ensure_mutable_graph_version(graph_version)

            try:
                await self._apply_compiled_graph_state(session, graph_version)
                logger.info(
                    "Compiled course graph version: graph_version_id={}, course_id={}, node_count={}, edge_count={}",
                    graph_version.id,
                    course_id,
                    graph_version.node_count,
                    graph_version.edge_count,
                )
            except ValueError as error:
                graph_version.status = CourseGraphVersionStatus.FAILED
                graph_version.error_message = str(error)
                graph_version.built_at = None
                await session.flush()
                logger.warning(
                    "Failed to compile course graph version: graph_version_id={}, course_id={}, error={}",
                    graph_version.id,
                    course_id,
                    error,
                )

            await session.refresh(graph_version)
            return CourseGraphVersionResponse.model_validate(graph_version)


    async def publish_graph_version(
        self,
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
    ) -> CourseGraphVersionResponse:
        async with self.storage_manager.session_ctx() as session:
            course = await self._load_course_or_404(session, course_id)
            graph_version = await self._load_graph_version_or_404(
                session,
                course_id,
                graph_version_id,
            )
            if graph_version.status != CourseGraphVersionStatus.READY:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only ready graph versions can be published",
                )

            course.current_graph_version_id = graph_version.id
            await session.flush()
            await session.refresh(graph_version)
            logger.info(
                "Published course graph version: course_id={}, graph_version_id={}, version_number={}",
                course_id,
                graph_version.id,
                graph_version.version_number,
            )
            return CourseGraphVersionResponse.model_validate(graph_version)


    async def _load_course_or_404(
        self,
        session: AsyncSession,
        course_id: uuid.UUID,
    ) -> Course:
        course = await session.get(Course, course_id)
        if course is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return course


    async def _load_course_node_or_404(
        self,
        session: AsyncSession,
        course_id: uuid.UUID,
        course_node_id: uuid.UUID,
    ) -> CourseNode:
        result = await session.execute(
            select(CourseNode).where(
                CourseNode.id == course_node_id,
                CourseNode.course_id == course_id,
            )
        )
        course_node = result.scalar_one_or_none()
        if course_node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course node not found",
            )
        return course_node


    async def _load_graph_version_or_404(
        self,
        session: AsyncSession,
        course_id: uuid.UUID,
        graph_version_id: uuid.UUID,
    ) -> CourseGraphVersion:
        result = await session.execute(
            select(CourseGraphVersion)
            .options(
                selectinload(CourseGraphVersion.version_nodes).selectinload(
                    CourseGraphVersionNode.course_node
                ),
                selectinload(CourseGraphVersion.version_nodes).selectinload(
                    CourseGraphVersionNode.lecture
                ),
                selectinload(CourseGraphVersion.edges),
            )
            .where(
                CourseGraphVersion.id == graph_version_id,
                CourseGraphVersion.course_id == course_id,
            )
        )
        graph_version = result.scalar_one_or_none()
        if graph_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course graph version not found",
            )
        return graph_version


    def _ensure_mutable_graph_version(self, graph_version: CourseGraphVersion) -> None:
        if graph_version.status == CourseGraphVersionStatus.READY:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ready graph version is immutable",
            )
        if graph_version.status == CourseGraphVersionStatus.ARCHIVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Archived graph version is immutable",
            )


    async def _validate_lecture_binding(
        self,
        session: AsyncSession,
        course_node_id: uuid.UUID,
        lecture_id: uuid.UUID | None,
    ) -> None:
        if lecture_id is None:
            return

        lecture = await session.get(Lecture, lecture_id)
        if lecture is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lecture not found",
            )
        if lecture.course_node_id != course_node_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lecture does not belong to the selected course node",
            )


    async def _load_graph_version_membership(
        self,
        session: AsyncSession,
        graph_version_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        result = await session.execute(
            select(CourseGraphVersionNode.course_node_id).where(
                CourseGraphVersionNode.graph_version_id == graph_version_id
            )
        )
        return set(result.scalars().all())


    async def _apply_compiled_graph_state(
        self,
        session: AsyncSession,
        graph_version: CourseGraphVersion,
    ) -> None:
        version_nodes = list(graph_version.version_nodes)
        edges = list(graph_version.edges)
        if not version_nodes:
            raise ValueError("Course graph version must contain at least one node")

        course_node_ids = {version_node.course_node_id for version_node in version_nodes}
        for version_node in version_nodes:
            lecture = version_node.lecture
            if lecture is not None and lecture.course_node_id != version_node.course_node_id:
                raise ValueError("Lecture binding must belong to the same course node")

        for edge in edges:
            if edge.prerequisite_course_node_id not in course_node_ids:
                raise ValueError("Prerequisite edge points to a node outside this graph version")
            if edge.dependent_course_node_id not in course_node_ids:
                raise ValueError("Dependent edge points to a node outside this graph version")

        topological_order = self._build_topological_order(version_nodes, edges)
        rank_by_course_node_id = {
            course_node_id: rank
            for rank, course_node_id in enumerate(topological_order)
        }
        for version_node in version_nodes:
            version_node.topological_rank = rank_by_course_node_id[version_node.course_node_id]

        graph_version.node_count = len(version_nodes)
        graph_version.edge_count = len(edges)
        graph_version.status = CourseGraphVersionStatus.READY
        graph_version.error_message = None
        graph_version.built_at = datetime.now(UTC)
        await session.flush()


    def _build_topological_order(
        self,
        version_nodes: list[CourseGraphVersionNode],
        edges: list[CourseGraphVersionEdge],
    ) -> list[uuid.UUID]:
        course_node_ids = [version_node.course_node_id for version_node in version_nodes]
        node_order = sorted(course_node_ids, key=str)
        dependents_by_node_id: dict[uuid.UUID, list[uuid.UUID]] = {
            course_node_id: []
            for course_node_id in node_order
        }
        indegree_by_node_id = {course_node_id: 0 for course_node_id in node_order}

        for edge in edges:
            dependents_by_node_id[edge.prerequisite_course_node_id].append(
                edge.dependent_course_node_id
            )
            indegree_by_node_id[edge.dependent_course_node_id] += 1

        ready_node_ids = deque(
            sorted(
                (
                    course_node_id
                    for course_node_id, indegree in indegree_by_node_id.items()
                    if indegree == 0
                ),
                key=str,
            )
        )
        topological_order: list[uuid.UUID] = []

        while ready_node_ids:
            course_node_id = ready_node_ids.popleft()
            topological_order.append(course_node_id)
            next_ready_node_ids: list[uuid.UUID] = []
            for dependent_course_node_id in sorted(
                dependents_by_node_id[course_node_id],
                key=str,
            ):
                indegree_by_node_id[dependent_course_node_id] -= 1
                if indegree_by_node_id[dependent_course_node_id] == 0:
                    next_ready_node_ids.append(dependent_course_node_id)

            for next_ready_node_id in sorted(next_ready_node_ids, key=str):
                ready_node_ids.append(next_ready_node_id)

        if len(topological_order) != len(node_order):
            raise ValueError("Course graph version contains a cycle")

        return topological_order


    def _build_graph_version_detail_response(
        self,
        graph_version: CourseGraphVersion,
    ) -> CourseGraphVersionDetailResponse:
        nodes = sorted(
            graph_version.version_nodes,
            key=lambda version_node: (
                version_node.topological_rank is None,
                version_node.topological_rank if version_node.topological_rank is not None else 0,
                str(version_node.course_node_id),
            ),
        )
        edges = sorted(
            graph_version.edges,
            key=lambda edge: (
                str(edge.prerequisite_course_node_id),
                str(edge.dependent_course_node_id),
            ),
        )
        return CourseGraphVersionDetailResponse(
            version=CourseGraphVersionResponse.model_validate(graph_version),
            nodes=[
                CourseGraphVersionNodeResponse.model_validate(version_node)
                for version_node in nodes
            ],
            edges=[
                CourseGraphVersionEdgeResponse.model_validate(edge)
                for edge in edges
            ],
        )
