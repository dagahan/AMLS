from __future__ import annotations

from datetime import datetime

from src.models.pydantic.common import AmlsSchema
from src.storage.db.enums import GraphAssessmentReviewStatus


class GeneratedAssessmentReview(AmlsSchema):
    status: GraphAssessmentReviewStatus
    review_text: str | None
    review_recommendations: list[str]
    review_model: str | None
    review_error: str | None
    generated_at: datetime | None


class ReviewCourseNodeContext(AmlsSchema):
    name: str
    description: str | None
    mastery_state: str
    is_frontier: bool
