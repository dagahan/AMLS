from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.logging import get_logger
from src.models.alchemy import Course, CourseGraphVersion, CourseGraphVersionNode, GraphAssessment
from src.models.pydantic.graph_assessment import (
    CourseMasteryHistoryResponse,
    GraphAssessmentResponse,
    GraphAssessmentStateResponse,
    MasteryHistoryItemResponse,
)
from src.services.graph_assessment.review_generation_service import (
    GraphAssessmentReviewService,
    ReviewCourseNodeContext,
)
from src.storage.db.enums import GraphAssessmentReviewStatus, TestAttemptKind
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class GraphAssessmentService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager
        self.review_service = GraphAssessmentReviewService()


    async def list_course_assessments(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> list[GraphAssessmentResponse]:
        async with self.storage_manager.session_ctx() as session:
            assessments = await self._load_course_assessments(session, user_id, course_id)
            logger.debug(
                "Listed course graph assessments",
                user_id=str(user_id),
                course_id=str(course_id),
                result_count=len(assessments),
            )
            return [
                build_graph_assessment_response(assessment)
                for assessment in assessments
            ]


    async def get_active_course_assessment(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> GraphAssessmentResponse:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(
                select(GraphAssessment)
                .join(
                    CourseGraphVersion,
                    CourseGraphVersion.id == GraphAssessment.graph_version_id,
                )
                .where(
                    GraphAssessment.user_id == user_id,
                    GraphAssessment.is_active.is_(True),
                    CourseGraphVersion.course_id == course_id,
                )
                .order_by(GraphAssessment.measured_at.desc(), GraphAssessment.id.desc())
            )
            graph_assessment = result.scalar_one_or_none()
            if graph_assessment is None:
                logger.debug(
                    "Active graph assessment was not found",
                    user_id=str(user_id),
                    course_id=str(course_id),
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Active graph assessment not found",
                )

            logger.debug(
                "Loaded active graph assessment",
                user_id=str(user_id),
                course_id=str(course_id),
                graph_assessment_id=str(graph_assessment.id),
            )
            return build_graph_assessment_response(graph_assessment)


    async def _load_course_assessments(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> list[GraphAssessment]:
        result = await session.execute(
            select(GraphAssessment)
            .options(selectinload(GraphAssessment.graph_version))
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


    async def list_course_mastery_history(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> CourseMasteryHistoryResponse:
        async with self.storage_manager.session_ctx() as session:
            assessments = await self._load_course_assessments(session, user_id, course_id)
            ordered_assessments = sorted(
                assessments,
                key=lambda assessment: (assessment.measured_at, assessment.created_at, str(assessment.id)),
            )
            previous_assessment: GraphAssessment | None = None
            items: list[MasteryHistoryItemResponse] = []
            for assessment in ordered_assessments:
                current_counts = _build_state_counts(assessment.state)
                previous_counts = _build_state_counts(previous_assessment.state) if previous_assessment else {
                    "learned": 0,
                    "ready": 0,
                    "locked": 0,
                    "failed": 0,
                }
                items.append(
                    MasteryHistoryItemResponse(
                        graph_assessment=build_graph_assessment_response(assessment),
                        learned_delta=current_counts["learned"] - previous_counts["learned"],
                        ready_delta=current_counts["ready"] - previous_counts["ready"],
                        locked_delta=current_counts["locked"] - previous_counts["locked"],
                        failed_delta=current_counts["failed"] - previous_counts["failed"],
                    )
                )
                previous_assessment = assessment
            return CourseMasteryHistoryResponse(items=items)


    async def retry_review(
        self,
        user_id: uuid.UUID,
        graph_assessment_id: uuid.UUID,
    ) -> GraphAssessmentResponse:
        async with self.storage_manager.session_ctx() as session:
            graph_assessment = await self._load_graph_assessment_or_404(
                session=session,
                user_id=user_id,
                graph_assessment_id=graph_assessment_id,
            )
            if graph_assessment.assessment_kind not in {
                TestAttemptKind.ENTRANCE,
                TestAttemptKind.GENERAL,
            }:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Review retry is only available for mastery-changing assessments",
                )

            graph_version = await self._load_graph_version_with_course_nodes(
                session,
                graph_assessment.graph_version_id,
            )
            course_title = graph_version.course.title if graph_version.course is not None else "Course"
            course_description = graph_version.course.description if graph_version.course is not None else None
            state_counts = _build_state_counts(graph_assessment.state)
            node_contexts = _build_review_node_contexts(
                graph_version=graph_version,
                graph_state=graph_assessment.state,
                metadata_json=graph_assessment.metadata_json,
            )
            generated_review = await self.review_service.generate_review(
                course_title=course_title,
                course_description=course_description,
                node_contexts=node_contexts,
                assessment_kind=graph_assessment.assessment_kind,
                state_confidence=graph_assessment.state_confidence,
                learned_count=state_counts["learned"],
                ready_count=state_counts["ready"],
                locked_count=state_counts["locked"],
                failed_count=state_counts["failed"],
            )
            graph_assessment.review_status = generated_review.status
            if generated_review.status == GraphAssessmentReviewStatus.SUCCEEDED:
                graph_assessment.review_text = generated_review.review_text
                graph_assessment.review_recommendations = generated_review.review_recommendations
                graph_assessment.review_error = None
                graph_assessment.review_generated_at = generated_review.generated_at
            else:
                graph_assessment.review_text = None
                graph_assessment.review_recommendations = _build_deterministic_recommendations(state_counts)
                graph_assessment.review_error = generated_review.review_error
                graph_assessment.review_generated_at = None
            graph_assessment.review_model = generated_review.review_model
            await session.flush()
            await session.refresh(graph_assessment)
            logger.info(
                "Retried graph assessment review",
                user_id=str(user_id),
                graph_assessment_id=str(graph_assessment.id),
                review_status=graph_assessment.review_status.value,
            )
            return build_graph_assessment_response(graph_assessment)


    async def _load_graph_assessment_or_404(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        graph_assessment_id: uuid.UUID,
    ) -> GraphAssessment:
        result = await session.execute(
            select(GraphAssessment).where(
                GraphAssessment.id == graph_assessment_id,
                GraphAssessment.user_id == user_id,
            )
        )
        graph_assessment = result.scalar_one_or_none()
        if graph_assessment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Graph assessment not found",
            )
        return graph_assessment


    async def _load_graph_version_with_course_nodes(
        self,
        session: AsyncSession,
        graph_version_id: uuid.UUID,
    ) -> CourseGraphVersion:
        result = await session.execute(
            select(CourseGraphVersion)
            .options(
                selectinload(CourseGraphVersion.course),
                selectinload(CourseGraphVersion.version_nodes).selectinload(
                    CourseGraphVersionNode.course_node
                ),
            )
            .where(CourseGraphVersion.id == graph_version_id)
        )
        graph_version = result.scalar_one_or_none()
        if graph_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course graph version not found",
            )
        return graph_version


def build_graph_assessment_response(graph_assessment: GraphAssessment) -> GraphAssessmentResponse:
    state = graph_assessment.state
    return GraphAssessmentResponse(
        id=graph_assessment.id,
        user_id=graph_assessment.user_id,
        graph_version_id=graph_assessment.graph_version_id,
        source_test_attempt_id=graph_assessment.source_test_attempt_id,
        state=GraphAssessmentStateResponse(
            learned_course_node_ids=_read_uuid_list(state, "learned_course_node_ids"),
            ready_course_node_ids=_read_uuid_list(state, "ready_course_node_ids"),
            locked_course_node_ids=_read_uuid_list(state, "locked_course_node_ids"),
            failed_course_node_ids=_read_uuid_list(state, "failed_course_node_ids"),
            answered_course_node_ids=_read_uuid_list(state, "answered_course_node_ids"),
        ),
        state_confidence=graph_assessment.state_confidence,
        is_active=graph_assessment.is_active,
        assessment_kind=graph_assessment.assessment_kind,
        metadata_json=graph_assessment.metadata_json,
        review_status=graph_assessment.review_status,
        review_text=graph_assessment.review_text,
        review_recommendations=graph_assessment.review_recommendations,
        review_model=graph_assessment.review_model,
        review_error=graph_assessment.review_error,
        review_generated_at=graph_assessment.review_generated_at,
        measured_at=graph_assessment.measured_at,
        created_at=graph_assessment.created_at,
        updated_at=graph_assessment.updated_at,
    )


def _read_uuid_list(state: dict[str, object], key: str) -> list[uuid.UUID]:
    raw_value = state.get(key)
    if not isinstance(raw_value, list):
        return []
    return [uuid.UUID(str(item)) for item in raw_value]


def _build_state_counts(state: dict[str, object]) -> dict[str, int]:
    return {
        "learned": len(_read_uuid_list(state, "learned_course_node_ids")),
        "ready": len(_read_uuid_list(state, "ready_course_node_ids")),
        "locked": len(_read_uuid_list(state, "locked_course_node_ids")),
        "failed": len(_read_uuid_list(state, "failed_course_node_ids")),
    }


def _build_deterministic_recommendations(state_counts: dict[str, int]) -> list[str]:
    recommendations: list[str] = []
    if state_counts["failed"] > 0:
        recommendations.append("Repeat recently failed problem types in a short practice test.")
    if state_counts["ready"] > 0:
        recommendations.append("Prioritize ready problem types to convert readiness into stable mastery.")
    if state_counts["locked"] > 0:
        recommendations.append("Strengthen prerequisite problem types to unlock dependent material.")
    if not recommendations:
        recommendations.append("Continue with regular practice to maintain stable mastery.")
    return recommendations


def _build_review_node_contexts(
    *,
    graph_version: CourseGraphVersion,
    graph_state: dict[str, object],
    metadata_json: dict[str, object] | None,
) -> list[ReviewCourseNodeContext]:
    frontier_node_ids = set(_read_string_list(metadata_json or {}, "inner_fringe_course_node_ids"))
    if not frontier_node_ids:
        frontier_node_ids = set(_read_string_list(metadata_json or {}, "legacy_frontier_course_node_ids"))

    mastery_by_course_node_id: dict[str, str] = {}
    for course_node_id in _read_string_list(graph_state, "learned_course_node_ids"):
        mastery_by_course_node_id[course_node_id] = "learned"
    for course_node_id in _read_string_list(graph_state, "ready_course_node_ids"):
        mastery_by_course_node_id.setdefault(course_node_id, "ready")
    for course_node_id in _read_string_list(graph_state, "failed_course_node_ids"):
        mastery_by_course_node_id.setdefault(course_node_id, "failed")
    for course_node_id in _read_string_list(graph_state, "locked_course_node_ids"):
        mastery_by_course_node_id.setdefault(course_node_id, "locked")

    return [
        ReviewCourseNodeContext(
            name=version_node.course_node.name,
            description=version_node.course_node.description,
            mastery_state=mastery_by_course_node_id.get(str(version_node.course_node_id), "unknown"),
            is_frontier=str(version_node.course_node_id) in frontier_node_ids,
        )
        for version_node in sorted(
            graph_version.version_nodes,
            key=lambda node: (
                node.topological_rank if node.topological_rank is not None else 10**9,
                str(node.course_node_id),
            ),
        )
    ]


def _read_string_list(state: dict[str, object], key: str) -> list[str]:
    raw_value = state.get(key)
    if not isinstance(raw_value, list):
        return []
    return [str(item) for item in raw_value]
