from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.logging import get_logger
from src.models.alchemy import (
    Course,
    CourseEnrollment,
    CourseGraphVersion,
    CourseGraphVersionNode,
    GraphAssessment,
    TestAttempt,
)
from src.models.alchemy.test import calculate_elapsed_solve_seconds
from src.models.pydantic.course import (
    CourseEnrollmentResponse,
    CourseCreate,
    CourseResponse,
    CourseGraphVersionResponse,
    CourseWorkspaceActionFlagsResponse,
    CourseWorkspaceAttemptResponse,
    CourseWorkspaceEdgeResponse,
    CourseWorkspaceNodeResponse,
    CourseWorkspaceResponse,
    GraphAssessmentReviewSnapshotResponse,
)
from src.services.graph_assessment.graph_assessment_service import build_graph_assessment_response
from src.storage.db.enums import TestAttemptStatus
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class CourseService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def create_course(self, author_id: uuid.UUID, data: CourseCreate) -> CourseResponse:
        async with self.storage_manager.session_ctx() as session:
            course = Course(
                author_id=author_id,
                title=data.title,
                description=data.description,
            )
            session.add(course)
            await session.flush()
            logger.info(
                "Created course: course_id={}, author_id={}, title={}",
                course.id,
                author_id,
                data.title,
            )
            return CourseResponse.model_validate(course)


    async def list_courses(self) -> list[CourseResponse]:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(select(Course).order_by(Course.created_at.desc()))
            courses = result.scalars().all()
            return [CourseResponse.model_validate(course) for course in courses]


    async def list_active_courses(self, user_id: uuid.UUID) -> list[CourseResponse]:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(
                select(Course)
                .join(CourseEnrollment, CourseEnrollment.course_id == Course.id)
                .where(
                    CourseEnrollment.user_id == user_id,
                    CourseEnrollment.is_active.is_(True),
                )
                .order_by(Course.created_at.desc())
            )
            courses = result.scalars().all()
            return [CourseResponse.model_validate(course) for course in courses]


    async def enroll_user(self, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseEnrollmentResponse:
        async with self.storage_manager.session_ctx() as session:
            course = await session.get(Course, course_id)
            if course is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )

            result = await session.execute(
                select(CourseEnrollment)
                .where(
                    CourseEnrollment.user_id == user_id,
                    CourseEnrollment.course_id == course_id,
                )
                .order_by(CourseEnrollment.created_at.desc(), CourseEnrollment.id.desc())
            )
            enrollments = result.scalars().all()

            if len(enrollments) == 0:
                course_enrollment = CourseEnrollment(
                    user_id=user_id,
                    course_id=course_id,
                    is_active=True,
                )
                session.add(course_enrollment)
                await session.flush()
                logger.info(
                    "Created course enrollment: enrollment_id={}, user_id={}, course_id={}",
                    course_enrollment.id,
                    user_id,
                    course_id,
                )
                await session.refresh(course_enrollment)
                return CourseEnrollmentResponse.model_validate(course_enrollment)

            course_enrollment = next(
                (enrollment for enrollment in enrollments if enrollment.is_active),
                enrollments[0],
            )

            if len(enrollments) > 1:
                logger.warning(
                    "Detected duplicate course enrollments and normalized state",
                    user_id=str(user_id),
                    course_id=str(course_id),
                    enrollment_count=len(enrollments),
                    selected_enrollment_id=str(course_enrollment.id),
                )

                for enrollment in enrollments:
                    if enrollment.id != course_enrollment.id:
                        enrollment.is_active = False

            if not course_enrollment.is_active:
                course_enrollment.is_active = True
                logger.info(
                    "Reactivated course enrollment: enrollment_id={}, user_id={}, course_id={}",
                    course_enrollment.id,
                    user_id,
                    course_id,
                )

            await session.flush()
            await session.refresh(course_enrollment)
            return CourseEnrollmentResponse.model_validate(course_enrollment)


    async def unenroll_user(self, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseEnrollmentResponse:
        async with self.storage_manager.session_ctx() as session:
            course = await session.get(Course, course_id)
            if course is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )

            result = await session.execute(
                select(CourseEnrollment).where(
                    CourseEnrollment.user_id == user_id,
                    CourseEnrollment.course_id == course_id,
                )
            )
            enrollment = result.scalar_one_or_none()
            if enrollment is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Enrollment not found",
                )

            enrollment.is_active = False
            await self._cancel_open_course_attempts(session, user_id, course_id)
            await session.flush()
            await session.refresh(enrollment)

            logger.info(
                "Deactivated course enrollment",
                user_id=str(user_id),
                course_id=str(course_id),
                enrollment_id=str(enrollment.id),
            )
            return CourseEnrollmentResponse.model_validate(enrollment)


    async def get_workspace(self, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseWorkspaceResponse:
        async with self.storage_manager.session_ctx() as session:
            await self._ensure_active_enrollment(session, user_id, course_id)
            course_result = await session.execute(
                select(Course)
                .options(
                    selectinload(Course.current_graph_version)
                    .selectinload(CourseGraphVersion.version_nodes)
                    .selectinload(CourseGraphVersionNode.course_node),
                    selectinload(Course.current_graph_version)
                    .selectinload(CourseGraphVersion.version_nodes)
                    .selectinload(CourseGraphVersionNode.lecture),
                    selectinload(Course.current_graph_version).selectinload(CourseGraphVersion.edges),
                )
                .where(Course.id == course_id)
            )
            course = course_result.scalar_one_or_none()
            if course is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Course not found",
                )
            if course.current_graph_version is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Course does not have a published graph version",
                )

            graph_version = course.current_graph_version
            assessments = await self._load_course_assessments(session, user_id, course_id)
            active_assessment = next(
                (
                    assessment
                    for assessment in assessments
                    if assessment.is_active
                ),
                None,
            )
            latest_assessment = assessments[0] if assessments else None
            active_attempt = await self._load_open_course_attempt(session, user_id, course_id)
            state_source = active_assessment or latest_assessment
            mastery_state_by_node_id = self._build_mastery_state_map(state_source)
            frontier_node_ids = self._read_frontier_node_ids(state_source)
            workspace_nodes = [
                CourseWorkspaceNodeResponse(
                    course_node_id=version_node.course_node_id,
                    problem_type_id=version_node.course_node.problem_type_id,
                    name=version_node.course_node.name,
                    lecture_id=version_node.lecture_id,
                    has_lecture=version_node.lecture_id is not None,
                    topological_rank=version_node.topological_rank,
                    mastery_state=mastery_state_by_node_id.get(version_node.course_node_id, "unknown"),
                    is_frontier=version_node.course_node_id in frontier_node_ids,
                )
                for version_node in sorted(
                    graph_version.version_nodes,
                    key=lambda node: (
                        node.topological_rank if node.topological_rank is not None else 10**9,
                        str(node.course_node_id),
                    ),
                )
            ]
            workspace_edges = [
                CourseWorkspaceEdgeResponse(
                    prerequisite_course_node_id=edge.prerequisite_course_node_id,
                    dependent_course_node_id=edge.dependent_course_node_id,
                )
                for edge in sorted(
                    graph_version.edges,
                    key=lambda edge: (
                        str(edge.prerequisite_course_node_id),
                        str(edge.dependent_course_node_id),
                    ),
                )
            ]
            latest_review = self._build_review_snapshot(latest_assessment)

            logger.info(
                "Loaded course workspace",
                user_id=str(user_id),
                course_id=str(course_id),
                graph_version_id=str(graph_version.id),
                node_count=len(workspace_nodes),
                edge_count=len(workspace_edges),
                has_active_attempt=active_attempt is not None,
                has_active_assessment=active_assessment is not None,
            )

            return CourseWorkspaceResponse(
                course=CourseResponse.model_validate(course),
                graph_version=self._build_graph_version_response(graph_version),
                nodes=workspace_nodes,
                edges=workspace_edges,
                active_test_attempt=self._build_workspace_attempt(active_attempt),
                active_graph_assessment=(
                    build_graph_assessment_response(active_assessment)
                    if active_assessment is not None
                    else None
                ),
                latest_graph_assessment=(
                    build_graph_assessment_response(latest_assessment)
                    if latest_assessment is not None
                    else None
                ),
                latest_review=latest_review,
                action_flags=CourseWorkspaceActionFlagsResponse(
                    can_start_entrance=active_assessment is None and active_attempt is None,
                    can_start_practice=active_attempt is None,
                    can_start_exam=active_attempt is None,
                    can_start_mistakes=active_attempt is None,
                    has_active_attempt=active_attempt is not None,
                    has_active_assessment=active_assessment is not None,
                ),
            )


    def _build_graph_version_response(
        self,
        graph_version: CourseGraphVersion,
    ) -> CourseGraphVersionResponse:
        return CourseGraphVersionResponse.model_validate(graph_version)


    def _build_workspace_attempt(
        self,
        attempt: TestAttempt | None,
    ) -> CourseWorkspaceAttemptResponse | None:
        if attempt is None:
            return None

        return CourseWorkspaceAttemptResponse(
            id=attempt.id,
            graph_version_id=attempt.graph_version_id,
            kind=attempt.kind,
            status=attempt.status,
            current_problem_id=attempt.current_problem_id,
            started_at=attempt.started_at,
            paused_at=attempt.paused_at,
            total_paused_seconds=attempt.total_paused_seconds,
            elapsed_solve_seconds=calculate_elapsed_solve_seconds(
                status=attempt.status,
                started_at=attempt.started_at,
                paused_at=attempt.paused_at,
                ended_at=attempt.ended_at,
                total_paused_seconds=attempt.total_paused_seconds,
            ),
            ended_at=attempt.ended_at,
            created_at=attempt.created_at,
            updated_at=attempt.updated_at,
        )


    def _build_review_snapshot(
        self,
        assessment: GraphAssessment | None,
    ) -> GraphAssessmentReviewSnapshotResponse | None:
        if assessment is None:
            return None

        return GraphAssessmentReviewSnapshotResponse(
            graph_assessment_id=assessment.id,
            review_status=assessment.review_status,
            review_text=assessment.review_text,
            review_recommendations=assessment.review_recommendations,
            review_model=assessment.review_model,
            review_error=assessment.review_error,
            review_generated_at=assessment.review_generated_at,
        )


    def _build_mastery_state_map(
        self,
        assessment: GraphAssessment | None,
    ) -> dict[uuid.UUID, str]:
        mastery_state_by_node_id: dict[uuid.UUID, str] = {}
        if assessment is None:
            return mastery_state_by_node_id

        state = assessment.state
        for course_node_id in self._read_uuid_list(state, "learned_course_node_ids"):
            mastery_state_by_node_id[course_node_id] = "learned"
        for course_node_id in self._read_uuid_list(state, "ready_course_node_ids"):
            if course_node_id not in mastery_state_by_node_id:
                mastery_state_by_node_id[course_node_id] = "ready"
        for course_node_id in self._read_uuid_list(state, "failed_course_node_ids"):
            if course_node_id not in mastery_state_by_node_id:
                mastery_state_by_node_id[course_node_id] = "failed"
        for course_node_id in self._read_uuid_list(state, "locked_course_node_ids"):
            if course_node_id not in mastery_state_by_node_id:
                mastery_state_by_node_id[course_node_id] = "locked"
        return mastery_state_by_node_id


    def _read_frontier_node_ids(self, assessment: GraphAssessment | None) -> set[uuid.UUID]:
        if assessment is None:
            return set()

        metadata_json = assessment.metadata_json
        frontier_ids = metadata_json.get("inner_fringe_course_node_ids")
        if not isinstance(frontier_ids, list):
            frontier_ids = metadata_json.get("legacy_frontier_course_node_ids")
        if not isinstance(frontier_ids, list):
            return set()

        parsed_ids: set[uuid.UUID] = set()
        for raw_value in frontier_ids:
            try:
                parsed_ids.add(uuid.UUID(str(raw_value)))
            except ValueError:
                continue
        return parsed_ids


    def _read_uuid_list(self, payload: dict[str, object], key: str) -> list[uuid.UUID]:
        raw_value = payload.get(key)
        if not isinstance(raw_value, list):
            return []

        parsed_values: list[uuid.UUID] = []
        for item in raw_value:
            try:
                parsed_values.append(uuid.UUID(str(item)))
            except ValueError:
                continue
        return parsed_values


    async def _ensure_active_enrollment(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(CourseEnrollment).where(
                CourseEnrollment.user_id == user_id,
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.is_active.is_(True),
            )
        )
        enrollment = result.scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Active enrollment is required",
            )


    async def _cancel_open_course_attempts(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(TestAttempt)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == TestAttempt.graph_version_id,
            )
            .where(
                TestAttempt.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
                TestAttempt.status.in_([TestAttemptStatus.ACTIVE, TestAttemptStatus.PAUSED]),
            )
        )
        attempts = list(result.scalars().all())
        for attempt in attempts:
            attempt.status = TestAttemptStatus.CANCELLED
            attempt.current_problem_id = None

        if attempts:
            logger.info(
                "Cancelled open attempts after unenroll",
                user_id=str(user_id),
                course_id=str(course_id),
                cancelled_count=len(attempts),
            )


    async def _load_open_course_attempt(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> TestAttempt | None:
        result = await session.execute(
            select(TestAttempt)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == TestAttempt.graph_version_id,
            )
            .where(
                TestAttempt.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
                TestAttempt.status.in_([TestAttemptStatus.ACTIVE, TestAttemptStatus.PAUSED]),
            )
            .order_by(TestAttempt.created_at.desc(), TestAttempt.id.desc())
        )
        return result.scalar_one_or_none()


    async def _load_course_assessments(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> list[GraphAssessment]:
        result = await session.execute(
            select(GraphAssessment)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == GraphAssessment.graph_version_id,
            )
            .where(
                GraphAssessment.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
            )
            .order_by(GraphAssessment.measured_at.desc(), GraphAssessment.id.desc())
        )
        return list(result.scalars().all())
