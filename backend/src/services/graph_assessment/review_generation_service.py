from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import re
from time import perf_counter
from typing import Any, Protocol

from src.core.logging import get_logger
from src.models.pydantic.llm import (
    LlmChatCompletionRequest,
    LlmChatMessage,
    LlmCompletionResult,
)
from src.models.pydantic.review_generation import (
    GeneratedAssessmentReview,
    ReviewCourseNodeContext,
)
from src.services.llm_client import LlmClient
from src.storage.db.enums import GraphAssessmentReviewStatus, TestAttemptKind


logger = get_logger(__name__)


class ReviewLlmClientProtocol(Protocol):
    async def create_chat_completion(
        self,
        *,
        request: LlmChatCompletionRequest,
        model_key: str | None = None,
    ) -> LlmCompletionResult:
        ...


class GraphAssessmentReviewService:
    DEFAULT_FALLBACK_RECOMMENDATION = (
        "Review weak problem types first, then retake a focused course test."
    )

    def __init__(
        self,
        llm_client: ReviewLlmClientProtocol | None = None,
    ) -> None:
        self.llm_client = llm_client or LlmClient()


    async def generate_review(
        self,
        *,
        course_title: str,
        course_description: str | None,
        node_contexts: list[ReviewCourseNodeContext],
        assessment_kind: TestAttemptKind,
        state_confidence: float,
        learned_count: int,
        ready_count: int,
        locked_count: int,
        failed_count: int,
    ) -> GeneratedAssessmentReview:
        started_at = perf_counter()
        confidence_percent = self._to_confidence_percent(state_confidence)

        prompt_payload: dict[str, object] = {
            "course_title": course_title,
            "course_description": course_description,
            "assessment_kind": assessment_kind.value,
            "confidence_percent": confidence_percent,
            "learned_count": learned_count,
            "ready_count": ready_count,
            "locked_count": locked_count,
            "failed_count": failed_count,
            "problem_types": [
                {
                    "name": node_context.name,
                    "description": node_context.description,
                    "mastery_state": node_context.mastery_state,
                    "is_frontier": node_context.is_frontier,
                }
                for node_context in node_contexts
            ],
        }
        logger.info(
            "Prepared graph assessment review prompt payload",
            course_title=course_title,
            assessment_kind=assessment_kind.value,
            problem_type_count=len(node_contexts),
            confidence_percent=confidence_percent,
            learned_count=learned_count,
            ready_count=ready_count,
            locked_count=locked_count,
            failed_count=failed_count,
        )
        completion_request = LlmChatCompletionRequest(
            temperature=0.2,
            messages=[
                LlmChatMessage(
                    role="system",
                    content=(
                        "You are an academic tutor writing concise student guidance. "
                        "Return JSON with one key: recommendations. "
                        "recommendations must contain 1 to 3 short practical next steps using course "
                        "and problem-type wording only. "
                        "Do not mention AI, LLM, model internals, JSON, prompts, system messages, "
                        "nodes, or graphs. Avoid long narrative critique."
                    ),
                ),
                LlmChatMessage(
                    role="user",
                    content=json.dumps(prompt_payload),
                ),
            ],
        )

        try:
            completion_result = await self.llm_client.create_chat_completion(
                request=completion_request,
                model_key=None,
            )
            review_recommendations = self._parse_completion_text(
                completion_text=completion_result.completion_text,
                confidence_percent=confidence_percent,
            )
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Generated graph assessment review",
                model=completion_result.model_name,
                base_url=completion_result.base_url,
                duration_ms=duration_ms,
                learned_count=learned_count,
                ready_count=ready_count,
                locked_count=locked_count,
                failed_count=failed_count,
                recommendation_count=len(review_recommendations),
            )
            return GeneratedAssessmentReview(
                status=GraphAssessmentReviewStatus.SUCCEEDED,
                review_text=None,
                review_recommendations=review_recommendations,
                review_model=completion_result.model_name,
                review_error=None,
                generated_at=datetime.now(UTC),
            )
        except (asyncio.TimeoutError, RuntimeError, ValueError) as error:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.warning(
                "Graph assessment review generation failed",
                duration_ms=duration_ms,
                error=str(error),
            )
            return GeneratedAssessmentReview(
                status=GraphAssessmentReviewStatus.FAILED,
                review_text=None,
                review_recommendations=[],
                review_model=None,
                review_error=str(error),
                generated_at=None,
            )


    def _parse_completion_text(
        self,
        *,
        completion_text: str,
        confidence_percent: int,
    ) -> list[str]:
        stripped_text = completion_text.strip()
        parsed_json = self._try_parse_json_payload(stripped_text)
        if parsed_json is not None:
            extracted_recommendations = self._extract_review_payload(parsed_json)
            return self._sanitize_recommendations(
                extracted_recommendations,
                confidence_percent=confidence_percent,
            )

        recommendations_from_text = [
            line.removeprefix("-").removeprefix("*").strip()
            for line in stripped_text.splitlines()
            if line.strip().startswith("-") or line.strip().startswith("*")
        ]
        if not recommendations_from_text and stripped_text != "":
            recommendations_from_text = [stripped_text]

        return self._sanitize_recommendations(
            recommendations_from_text,
            confidence_percent=confidence_percent,
        )


    def _try_parse_json_payload(self, completion_text: str) -> dict[str, object] | None:
        parsed_direct = self._parse_json_object(completion_text)
        if parsed_direct is not None:
            return parsed_direct

        for candidate_json_text in self._extract_fenced_json_candidates(completion_text):
            parsed_candidate = self._parse_json_object(candidate_json_text)
            if parsed_candidate is not None:
                return parsed_candidate

        first_brace_index = completion_text.find("{")
        last_brace_index = completion_text.rfind("}")
        if first_brace_index == -1 or last_brace_index == -1 or first_brace_index >= last_brace_index:
            return None

        braced_candidate = completion_text[first_brace_index:last_brace_index + 1]
        return self._parse_json_object(braced_candidate)


    def _parse_json_object(self, raw_text: str) -> dict[str, object] | None:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, dict):
            return parsed
        return None


    def _extract_fenced_json_candidates(self, raw_text: str) -> list[str]:
        return [
            match.group(1).strip()
            for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE)
            if match.group(1).strip() != ""
        ]


    def _extract_review_payload(self, parsed_json: dict[str, object]) -> list[str]:
        raw_recommendations = parsed_json.get(
            "recommendations",
            parsed_json.get(
                "review_recommendations",
                parsed_json.get("advice", []),
            ),
        )
        if isinstance(raw_recommendations, str):
            recommendations = [
                line.removeprefix("-").strip()
                for line in raw_recommendations.splitlines()
                if line.strip() != ""
            ]
        elif isinstance(raw_recommendations, list):
            recommendations = [
                str(item).strip()
                for item in raw_recommendations
                if str(item).strip() != ""
            ]
        else:
            recommendations = []

        return recommendations


    def _sanitize_recommendations(
        self,
        recommendations: list[str],
        *,
        confidence_percent: int,
    ) -> list[str]:
        normalized_recommendations: list[str] = []
        for recommendation in recommendations:
            cleaned_recommendation = self._sanitize_student_text(
                text=recommendation,
                confidence_percent=confidence_percent,
                append_confidence=False,
            )
            if cleaned_recommendation == "":
                continue
            if cleaned_recommendation in normalized_recommendations:
                continue
            normalized_recommendations.append(cleaned_recommendation)
            if len(normalized_recommendations) == 3:
                break

        if normalized_recommendations:
            return normalized_recommendations

        return [self.DEFAULT_FALLBACK_RECOMMENDATION]


    def _sanitize_student_text(
        self,
        *,
        text: str,
        confidence_percent: int | None,
        append_confidence: bool,
    ) -> str:
        cleaned_text = text.replace("`", "")
        cleaned_text = re.sub(
            r"(?i)\b(?:as an ai language model|as a language model|as an ai)\b",
            "",
            cleaned_text,
        )
        cleaned_text = re.sub(
            r"(?i)\b(?:llm|model internals?|json response|json output|system prompt|system data|prompt)\b",
            "",
            cleaned_text,
        )
        cleaned_text = re.sub(
            r"(?i)\bnodes\b",
            "problem types",
            cleaned_text,
        )
        cleaned_text = re.sub(
            r"(?i)\bnode\b",
            "problem type",
            cleaned_text,
        )
        cleaned_text = re.sub(
            r"(?i)\bgraphs\b",
            "courses",
            cleaned_text,
        )
        cleaned_text = re.sub(
            r"(?i)\bgraph\b",
            "course",
            cleaned_text,
        )
        if confidence_percent is not None:
            cleaned_text = re.sub(
                r"(?i)(confidence[^0-9%]{0,32})([0-9]+(?:\.[0-9]+)?)(?:\s*%?)",
                lambda match: f"{match.group(1)}{confidence_percent}%",
                cleaned_text,
            )
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

        if append_confidence and confidence_percent is not None and cleaned_text != "" and "confidence" not in cleaned_text.lower():
            return f"{cleaned_text} Current confidence is {confidence_percent}%."

        return cleaned_text


    def _to_confidence_percent(self, state_confidence: float) -> int:
        bounded_confidence = max(0.0, min(1.0, float(state_confidence)))
        return int(round(bounded_confidence * 100))


__all__ = [
    "GeneratedAssessmentReview",
    "GraphAssessmentReviewService",
    "ReviewCourseNodeContext",
]
