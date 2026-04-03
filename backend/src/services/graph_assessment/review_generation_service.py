from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from time import perf_counter
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from src.config import get_app_config
from src.core.logging import get_logger
from src.storage.db.enums import GraphAssessmentReviewStatus, TestAttemptKind


logger = get_logger(__name__)
LOCAL_LMS_BASE_URL_CANDIDATES = (
    "http://127.0.0.1:1234/v1",
    "http://localhost:1234/v1",
)


@dataclass(slots=True)
class GeneratedAssessmentReview:
    status: GraphAssessmentReviewStatus
    review_text: str | None
    review_recommendations: list[str]
    review_model: str | None
    review_error: str | None
    generated_at: datetime | None


class GraphAssessmentReviewService:
    async def generate_review(
        self,
        *,
        course_title: str,
        assessment_kind: TestAttemptKind,
        state_confidence: float,
        learned_count: int,
        ready_count: int,
        locked_count: int,
        failed_count: int,
    ) -> GeneratedAssessmentReview:
        app_config = get_app_config()
        started_at = perf_counter()
        resolved_base_url = app_config.infra.lms_base_url

        resolution_started_at = perf_counter()
        try:
            resolved_base_url = await asyncio.wait_for(
                asyncio.to_thread(
                    self._resolve_working_base_url,
                    configured_base_url=app_config.infra.lms_base_url,
                    api_key=app_config.infra.lms_api_key,
                    timeout_seconds=max(
                        app_config.infra.lms_timeout_seconds,
                        app_config.infra.lms_auto_wake_timeout_seconds,
                    ),
                ),
                timeout=float(
                    max(
                        app_config.infra.lms_timeout_seconds,
                        app_config.infra.lms_auto_wake_timeout_seconds,
                    )
                )
                * 4.0
                + 1.0,
            )
            if resolved_base_url != app_config.infra.lms_base_url:
                logger.warning(
                    "LM Studio base URL fallback selected",
                    configured_base_url=app_config.infra.lms_base_url,
                    selected_base_url=resolved_base_url,
                    duration_ms=round((perf_counter() - resolution_started_at) * 1000, 2),
                )
            else:
                logger.info(
                    "LM Studio configured base URL is reachable",
                    configured_base_url=app_config.infra.lms_base_url,
                    duration_ms=round((perf_counter() - resolution_started_at) * 1000, 2),
                )
        except (asyncio.TimeoutError, urllib_error.URLError, RuntimeError, ValueError) as error:
            logger.warning(
                "LM Studio base URL resolution failed",
                configured_base_url=app_config.infra.lms_base_url,
                duration_ms=round((perf_counter() - resolution_started_at) * 1000, 2),
                error=str(error),
            )

        auto_wake_started_at = perf_counter()
        if app_config.infra.lms_auto_wake_enabled:
            logger.info(
                "LM Studio auto-wake started",
                model=app_config.infra.lms_model,
                base_url=resolved_base_url,
                timeout_seconds=app_config.infra.lms_auto_wake_timeout_seconds,
                retry_count=app_config.infra.lms_auto_wake_retry_count,
            )
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        self._ensure_model_available,
                        base_url=resolved_base_url,
                        api_key=app_config.infra.lms_api_key,
                        model=app_config.infra.lms_model,
                        timeout_seconds=app_config.infra.lms_auto_wake_timeout_seconds,
                        retry_count=app_config.infra.lms_auto_wake_retry_count,
                    ),
                    timeout=float(app_config.infra.lms_auto_wake_timeout_seconds)
                    * float(app_config.infra.lms_auto_wake_retry_count + 1)
                    + 1.0,
                )
                logger.info(
                    "LM Studio auto-wake completed",
                    model=app_config.infra.lms_model,
                    base_url=resolved_base_url,
                    duration_ms=round((perf_counter() - auto_wake_started_at) * 1000, 2),
                )
            except (asyncio.TimeoutError, urllib_error.URLError, RuntimeError, ValueError) as error:
                logger.warning(
                    "LM Studio auto-wake failed",
                    model=app_config.infra.lms_model,
                    base_url=resolved_base_url,
                    duration_ms=round((perf_counter() - auto_wake_started_at) * 1000, 2),
                    error=str(error),
                )

        prompt_payload = {
            "course_title": course_title,
            "assessment_kind": assessment_kind.value,
            "state_confidence": round(state_confidence, 6),
            "learned_count": learned_count,
            "ready_count": ready_count,
            "locked_count": locked_count,
            "failed_count": failed_count,
        }
        request_payload = {
            "model": app_config.infra.lms_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an adaptive learning assistant. Return compact JSON with keys "
                        "review_text and recommendations. recommendations must be a short array "
                        "of practical next steps."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload),
                },
            ],
        }

        try:
            raw_response_payload = await asyncio.wait_for(
                asyncio.to_thread(
                    self._request_chat_completion,
                    resolved_base_url,
                    app_config.infra.lms_api_key,
                    request_payload,
                ),
                timeout=float(app_config.infra.lms_timeout_seconds) + 1.0,
            )
            completion_text = self._extract_completion_content(raw_response_payload)
            review_text, review_recommendations = self._parse_completion_text(completion_text)
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Generated LM Studio review",
                model=app_config.infra.lms_model,
                base_url=resolved_base_url,
                duration_ms=duration_ms,
                learned_count=learned_count,
                ready_count=ready_count,
                locked_count=locked_count,
                failed_count=failed_count,
            )
            return GeneratedAssessmentReview(
                status=GraphAssessmentReviewStatus.SUCCEEDED,
                review_text=review_text,
                review_recommendations=review_recommendations,
                review_model=app_config.infra.lms_model,
                review_error=None,
                generated_at=datetime.now(UTC),
            )
        except (asyncio.TimeoutError, urllib_error.URLError, RuntimeError, ValueError) as error:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.warning(
                "LM Studio review generation failed",
                model=app_config.infra.lms_model,
                base_url=resolved_base_url,
                duration_ms=duration_ms,
                error=str(error),
            )
            return GeneratedAssessmentReview(
                status=GraphAssessmentReviewStatus.FAILED,
                review_text=None,
                review_recommendations=[],
                review_model=app_config.infra.lms_model,
                review_error=str(error),
                generated_at=None,
            )


    def _request_chat_completion(
        self,
        base_url: str,
        api_key: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        normalized_base_url = base_url.rstrip("/")
        request_url = f"{normalized_base_url}/chat/completions"
        request_body = json.dumps(payload).encode("utf-8")
        http_request = urllib_request.Request(
            request_url,
            data=request_body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib_request.urlopen(
            http_request,
            timeout=float(get_app_config().infra.lms_timeout_seconds),
        ) as http_response:
            raw_payload = http_response.read().decode("utf-8")
        parsed_payload = json.loads(raw_payload)
        if not isinstance(parsed_payload, dict):
            raise RuntimeError("LM Studio response is not a JSON object")
        return parsed_payload


    def _ensure_model_available(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        retry_count: int,
    ) -> None:
        normalized_retry_count = max(0, retry_count)
        management_base_url = self._build_management_base_url(base_url)
        last_error: Exception | None = None

        for attempt_index in range(normalized_retry_count + 1):
            try:
                loaded_model_ids = self._request_loaded_model_ids(
                    management_base_url=management_base_url,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
                if self._is_model_loaded(requested_model=model, loaded_model_ids=loaded_model_ids):
                    return

                self._request_model_load(
                    management_base_url=management_base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
                loaded_model_ids = self._request_loaded_model_ids(
                    management_base_url=management_base_url,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
                if self._is_model_loaded(requested_model=model, loaded_model_ids=loaded_model_ids):
                    return

                last_error = RuntimeError(f"Model '{model}' is still unavailable after load call")
            except (urllib_error.URLError, RuntimeError, ValueError) as error:
                last_error = error

            if attempt_index < normalized_retry_count:
                time.sleep(0.25)

        if last_error is None:
            raise RuntimeError(f"Model '{model}' is unavailable")
        raise RuntimeError(str(last_error))


    def _resolve_working_base_url(
        self,
        *,
        configured_base_url: str,
        api_key: str,
        timeout_seconds: int,
    ) -> str:
        candidate_base_urls = self._build_candidate_base_urls(configured_base_url)
        probe_errors: list[str] = []
        for candidate_base_url in candidate_base_urls:
            candidate_started_at = perf_counter()
            try:
                self._request_json(
                    url=f"{candidate_base_url}/models",
                    method="GET",
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                    payload=None,
                )
                logger.info(
                    "LM Studio base URL probe succeeded",
                    candidate_base_url=candidate_base_url,
                    duration_ms=round((perf_counter() - candidate_started_at) * 1000, 2),
                )
                return candidate_base_url
            except (urllib_error.URLError, RuntimeError, ValueError) as error:
                probe_errors.append(f"{candidate_base_url}: {error}")
                logger.warning(
                    "LM Studio base URL probe failed",
                    candidate_base_url=candidate_base_url,
                    duration_ms=round((perf_counter() - candidate_started_at) * 1000, 2),
                    error=str(error),
                )

        joined_errors = " | ".join(probe_errors)
        raise RuntimeError(f"No reachable LM Studio base URL candidates. {joined_errors}")


    def _build_candidate_base_urls(self, configured_base_url: str) -> list[str]:
        raw_candidates = [configured_base_url, *LOCAL_LMS_BASE_URL_CANDIDATES]
        unique_candidates: list[str] = []
        for raw_candidate in raw_candidates:
            normalized_candidate = raw_candidate.strip().rstrip("/")
            if normalized_candidate == "" or normalized_candidate in unique_candidates:
                continue
            unique_candidates.append(normalized_candidate)
        return unique_candidates


    def _build_management_base_url(self, base_url: str) -> str:
        normalized_base_url = base_url.rstrip("/")
        if normalized_base_url.endswith("/v1"):
            return normalized_base_url[:-3]
        return normalized_base_url


    def _request_loaded_model_ids(
        self,
        *,
        management_base_url: str,
        api_key: str,
        timeout_seconds: int,
    ) -> set[str]:
        response_payload = self._request_json(
            url=f"{management_base_url}/api/v1/models",
            method="GET",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            payload=None,
        )
        loaded_model_ids: set[str] = set()

        raw_data = response_payload.get("data")
        if isinstance(raw_data, list):
            for item in raw_data:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id")
                if isinstance(item_id, str) and item_id.strip() != "":
                    loaded_model_ids.add(item_id)
            return loaded_model_ids

        raw_models = response_payload.get("models")
        if isinstance(raw_models, list):
            for model_item in raw_models:
                if not isinstance(model_item, dict):
                    continue
                model_key = model_item.get("key")
                loaded_instances = model_item.get("loaded_instances")
                if not isinstance(loaded_instances, list):
                    continue
                if len(loaded_instances) == 0:
                    continue
                if isinstance(model_key, str) and model_key.strip() != "":
                    loaded_model_ids.add(model_key)
                for instance_item in loaded_instances:
                    if not isinstance(instance_item, dict):
                        continue
                    instance_id = instance_item.get("id")
                    if isinstance(instance_id, str) and instance_id.strip() != "":
                        loaded_model_ids.add(instance_id)
            return loaded_model_ids

        raise RuntimeError("LM Studio models response does not include data or models list")


    def _is_model_loaded(self, *, requested_model: str, loaded_model_ids: set[str]) -> bool:
        if requested_model in loaded_model_ids:
            return True
        return any(
            loaded_model_id.startswith(f"{requested_model}:")
            for loaded_model_id in loaded_model_ids
        )
        return loaded_model_ids


    def _request_model_load(
        self,
        *,
        management_base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        self._request_json(
            url=f"{management_base_url}/api/v1/models/load",
            method="POST",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            payload={
                "model": model,
            },
        )


    def _request_json(
        self,
        *,
        url: str,
        method: str,
        api_key: str,
        timeout_seconds: int,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        request_body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        if request_body is not None:
            headers["Content-Type"] = "application/json"

        http_request = urllib_request.Request(
            url,
            data=request_body,
            method=method,
            headers=headers,
        )
        try:
            with urllib_request.urlopen(http_request, timeout=float(timeout_seconds)) as http_response:
                raw_payload = http_response.read().decode("utf-8")
        except urllib_error.HTTPError as error:
            response_payload = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"LM Studio request failed with status {error.code}: {response_payload}"
            ) from error

        if raw_payload.strip() == "":
            return {}
        parsed_payload = json.loads(raw_payload)
        if not isinstance(parsed_payload, dict):
            raise RuntimeError("LM Studio response payload is not a JSON object")
        return parsed_payload


    def _extract_completion_content(self, payload: dict[str, object]) -> str:
        raw_choices = payload.get("choices")
        if not isinstance(raw_choices, list) or not raw_choices:
            raise RuntimeError("LM Studio response does not include choices")
        first_choice = raw_choices[0]
        if not isinstance(first_choice, dict):
            raise RuntimeError("LM Studio response choice is malformed")
        raw_message = first_choice.get("message")
        if not isinstance(raw_message, dict):
            raise RuntimeError("LM Studio response message is malformed")
        raw_content = raw_message.get("content")
        if not isinstance(raw_content, str) or raw_content.strip() == "":
            raise RuntimeError("LM Studio response content is empty")
        return raw_content


    def _parse_completion_text(self, completion_text: str) -> tuple[str, list[str]]:
        stripped_text = completion_text.strip()
        parsed_json = self._try_parse_json_payload(stripped_text)
        if parsed_json is not None:
            review_text = str(parsed_json.get("review_text", "")).strip()
            recommendations = parsed_json.get("recommendations", [])
            if not isinstance(recommendations, list):
                recommendations = []
            normalized_recommendations = [
                str(item).strip()
                for item in recommendations
                if str(item).strip() != ""
            ]
            if review_text != "":
                return review_text, normalized_recommendations

        recommendations_from_text = [
            line[1:].strip()
            for line in stripped_text.splitlines()
            if line.strip().startswith("-")
        ]
        return stripped_text, recommendations_from_text


    def _try_parse_json_payload(self, completion_text: str) -> dict[str, object] | None:
        try:
            parsed = json.loads(completion_text)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, dict):
            return parsed
        return None
