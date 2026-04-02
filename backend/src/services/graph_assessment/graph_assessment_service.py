from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.logging import get_logger
from src.models.alchemy import CourseGraphVersion, GraphAssessment
from src.models.pydantic.graph_assessment import (
    GraphAssessmentResponse,
    GraphAssessmentStateResponse,
)
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class GraphAssessmentService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


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
        measured_at=graph_assessment.measured_at,
        created_at=graph_assessment.created_at,
        updated_at=graph_assessment.updated_at,
    )


def _read_uuid_list(state: dict[str, object], key: str) -> list[uuid.UUID]:
    raw_value = state.get(key)
    if not isinstance(raw_value, list):
        return []
    return [uuid.UUID(str(item)) for item in raw_value]
