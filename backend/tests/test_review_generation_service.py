import json

import pytest

from src.models.pydantic.llm import LlmChatCompletionRequest, LlmCompletionResult
from src.services.graph_assessment.review_generation_service import (
    GraphAssessmentReviewService,
    ReviewCourseNodeContext,
)
from src.storage.db.enums import GraphAssessmentReviewStatus, TestAttemptKind as AttemptKind


class LlmClientStub:
    def __init__(
        self,
        *,
        completion_result: LlmCompletionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.completion_result = completion_result
        self.error = error
        self.call_count = 0
        self.last_model_key: str | None | object = object()
        self.last_request: LlmChatCompletionRequest | None = None


    async def create_chat_completion(
        self,
        *,
        request: LlmChatCompletionRequest,
        model_key: str | None = None,
    ) -> LlmCompletionResult:
        self.call_count += 1
        self.last_request = request
        self.last_model_key = model_key
        if self.error is not None:
            raise self.error
        if self.completion_result is None:
            raise RuntimeError("Missing completion result in LLM client stub")
        return self.completion_result


def build_node_contexts() -> list[ReviewCourseNodeContext]:
    return [
        ReviewCourseNodeContext(
            name="solve linear equations",
            description="This problem type develops linear-equation solving with consistent transformation checks.",
            mastery_state="learned",
            is_frontier=False,
        ),
        ReviewCourseNodeContext(
            name="solve systems of equations",
            description="This problem type trains substitution and elimination in exam-style systems.",
            mastery_state="ready",
            is_frontier=True,
        ),
    ]


@pytest.mark.asyncio
async def test_generate_review_returns_success_and_uses_llm_client() -> None:
    llm_client = LlmClientStub(
        completion_result=LlmCompletionResult(
            model_name="qwen2.5-coder-3b-instruct-mlx",
            base_url="http://127.0.0.1:1234/v1",
            completion_text=json.dumps(
                {
                    "recommendations": ["Practice vectors", "Review fractions"],
                }
            ),
        )
    )
    service = GraphAssessmentReviewService(llm_client=llm_client)

    generated_review = await service.generate_review(
        course_title="Profile Mathematics (Grades 10-11)",
        course_description=(
            "Profile Mathematics builds prerequisite-aware mastery across algebra, functions, and geometry."
        ),
        node_contexts=build_node_contexts(),
        assessment_kind=AttemptKind.ENTRANCE,
        state_confidence=0.72,
        learned_count=20,
        ready_count=14,
        locked_count=8,
        failed_count=3,
    )

    assert llm_client.call_count == 1
    assert llm_client.last_model_key is None
    assert generated_review.status == GraphAssessmentReviewStatus.SUCCEEDED
    assert generated_review.review_text is None
    assert generated_review.review_recommendations == ["Practice vectors", "Review fractions"]
    assert generated_review.review_error is None
    assert generated_review.generated_at is not None


@pytest.mark.asyncio
async def test_generate_review_returns_failed_status_when_completion_fails() -> None:
    llm_client = LlmClientStub(error=RuntimeError("LLM completion failed"))
    service = GraphAssessmentReviewService(llm_client=llm_client)

    generated_review = await service.generate_review(
        course_title="Profile Mathematics (Grades 10-11)",
        course_description=(
            "Profile Mathematics builds prerequisite-aware mastery across algebra, functions, and geometry."
        ),
        node_contexts=build_node_contexts(),
        assessment_kind=AttemptKind.ENTRANCE,
        state_confidence=0.44,
        learned_count=10,
        ready_count=9,
        locked_count=20,
        failed_count=8,
    )

    assert generated_review.status == GraphAssessmentReviewStatus.FAILED
    assert generated_review.review_text is None
    assert generated_review.review_recommendations == []
    assert generated_review.review_error == "LLM completion failed"
    assert generated_review.generated_at is None
    assert generated_review.review_model is None


@pytest.mark.asyncio
async def test_generate_review_includes_course_and_problem_type_context_in_prompt() -> None:
    llm_client = LlmClientStub(
        completion_result=LlmCompletionResult(
            model_name="qwen2.5-coder-3b-instruct-mlx",
            base_url="http://127.0.0.1:1234/v1",
            completion_text=json.dumps(
                {
                    "recommendations": ["Start frontier problem-type practice now"],
                }
            ),
        )
    )
    service = GraphAssessmentReviewService(llm_client=llm_client)

    generated_review = await service.generate_review(
        course_title="Profile Mathematics (Grades 10-11)",
        course_description=(
            "Detailed profile-mathematics course with full problem-type structure and prerequisites, "
            "and mastery diagnostics for every topic."
        ),
        node_contexts=build_node_contexts(),
        assessment_kind=AttemptKind.GENERAL,
        state_confidence=0.88,
        learned_count=32,
        ready_count=18,
        locked_count=31,
        failed_count=6,
    )

    assert llm_client.last_request is not None
    assert len(llm_client.last_request.messages) == 2
    parsed_content = json.loads(llm_client.last_request.messages[1].content)
    assert parsed_content["course_description"].startswith("Detailed profile-mathematics course")
    assert len(parsed_content["problem_types"]) == 2
    assert parsed_content["problem_types"][0]["name"] == "solve linear equations"
    assert parsed_content["problem_types"][1]["is_frontier"] is True
    assert generated_review.status == GraphAssessmentReviewStatus.SUCCEEDED
    assert generated_review.review_text is None


def test_parse_completion_text_handles_fenced_json_and_caps_recommendations() -> None:
    service = GraphAssessmentReviewService(llm_client=LlmClientStub(error=RuntimeError("unused")))
    recommendations = service._parse_completion_text(
        completion_text=(
            "```json\n"
            "{"
            "\"review_text\": \"As an AI language model, your confidence is low (0.612038). "
            "Focus on failed nodes first.\","
            "\"recommendations\": [\"Repeat failed nodes\", \"Recheck prerequisite algebra\", \"Work on graph basics\", \"Extra item\"]"
            "}\n"
            "```"
        ),
        confidence_percent=61,
    )

    assert recommendations == [
        "Repeat failed problem types",
        "Recheck prerequisite algebra",
        "Work on course basics",
    ]


def test_parse_completion_text_returns_fallback_advice_when_no_recommendations() -> None:
    service = GraphAssessmentReviewService(llm_client=LlmClientStub(error=RuntimeError("unused")))
    recommendations = service._parse_completion_text(
        completion_text="{\"review_text\": \"No list\"}",
        confidence_percent=64,
    )

    assert recommendations == [service.DEFAULT_FALLBACK_RECOMMENDATION]
