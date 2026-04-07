from __future__ import annotations

import asyncio
import json
from time import perf_counter
import time
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from src.core.logging import get_logger
from src.models.pydantic.llm import (
    LlmChatCompletionRequest,
    LlmCompletionResult,
    LlmModelDefinition,
)


logger = get_logger(__name__)


class LmsStudioRuntimeClient:
    async def create_chat_completion(
        self,
        *,
        model_definition: LlmModelDefinition,
        api_key: str,
        request: LlmChatCompletionRequest,
        completion_timeout_seconds: int,
        auto_wake_enabled: bool,
        auto_wake_timeout_seconds: int,
        auto_wake_retry_count: int,
    ) -> LlmCompletionResult:
        started_at = perf_counter()
        resolved_base_url = model_definition.model_base_url

        resolution_started_at = perf_counter()
        try:
            candidate_base_urls = self._build_candidate_base_urls(model_definition.model_base_url)
            probe_timeout_seconds = self._build_probe_timeout_seconds(
                timeout_seconds=completion_timeout_seconds,
                candidate_count=len(candidate_base_urls),
            )
            resolved_base_url = await asyncio.wait_for(
                asyncio.to_thread(
                    self._resolve_working_base_url,
                    configured_base_url=model_definition.model_base_url,
                    api_key=api_key,
                    timeout_seconds=max(completion_timeout_seconds, auto_wake_timeout_seconds),
                ),
                timeout=probe_timeout_seconds,
            )
            if resolved_base_url != model_definition.model_base_url:
                logger.warning(
                    "LM Studio base URL fallback selected",
                    configured_base_url=model_definition.model_base_url,
                    selected_base_url=resolved_base_url,
                    duration_ms=round((perf_counter() - resolution_started_at) * 1000, 2),
                )
            else:
                logger.info(
                    "LM Studio configured base URL is reachable",
                    configured_base_url=model_definition.model_base_url,
                    duration_ms=round((perf_counter() - resolution_started_at) * 1000, 2),
                )
        except (asyncio.TimeoutError, urllib_error.URLError, RuntimeError, ValueError) as error:
            logger.warning(
                "LM Studio base URL resolution failed",
                configured_base_url=model_definition.model_base_url,
                duration_ms=round((perf_counter() - resolution_started_at) * 1000, 2),
                error=str(error),
            )

        auto_wake_started_at = perf_counter()
        if auto_wake_enabled:
            logger.info(
                "LM Studio auto-wake started",
                model=model_definition.model_name,
                base_url=resolved_base_url,
                timeout_seconds=auto_wake_timeout_seconds,
                retry_count=auto_wake_retry_count,
            )
            try:
                auto_wake_budget_seconds = self._build_auto_wake_timeout_budget(
                    timeout_seconds=auto_wake_timeout_seconds,
                    retry_count=auto_wake_retry_count,
                )
                await asyncio.wait_for(
                    asyncio.to_thread(
                        self._ensure_model_available,
                        base_url=resolved_base_url,
                        api_key=api_key,
                        model=model_definition.model_name,
                        timeout_seconds=auto_wake_timeout_seconds,
                        retry_count=auto_wake_retry_count,
                    ),
                    timeout=auto_wake_budget_seconds,
                )
                logger.info(
                    "LM Studio auto-wake completed",
                    model=model_definition.model_name,
                    base_url=resolved_base_url,
                    duration_ms=round((perf_counter() - auto_wake_started_at) * 1000, 2),
                )
            except (asyncio.TimeoutError, urllib_error.URLError, RuntimeError, ValueError) as error:
                logger.warning(
                    "LM Studio auto-wake failed",
                    model=model_definition.model_name,
                    base_url=resolved_base_url,
                    duration_ms=round((perf_counter() - auto_wake_started_at) * 1000, 2),
                    error=str(error),
                )

        request_payload = {
            "model": model_definition.model_name,
            "temperature": request.temperature,
            "messages": [
                message.model_dump(mode="python")
                for message in request.messages
            ],
        }
        raw_response_payload = await asyncio.wait_for(
            asyncio.to_thread(
                self._request_chat_completion,
                resolved_base_url,
                api_key,
                request_payload,
                completion_timeout_seconds,
            ),
            timeout=float(max(1, completion_timeout_seconds)) + 1.0,
        )
        completion_text = self._extract_completion_content(raw_response_payload)
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "Created LM Studio chat completion",
            model=model_definition.model_name,
            base_url=resolved_base_url,
            duration_ms=duration_ms,
            message_count=len(request.messages),
        )
        return LlmCompletionResult(
            model_name=model_definition.model_name,
            base_url=resolved_base_url,
            completion_text=completion_text,
        )


    def _build_probe_timeout_seconds(self, *, timeout_seconds: int, candidate_count: int) -> float:
        safe_timeout_seconds = max(1, timeout_seconds)
        safe_candidate_count = max(1, candidate_count)
        return float(safe_timeout_seconds * safe_candidate_count) + 1.0


    def _build_auto_wake_timeout_budget(self, *, timeout_seconds: int, retry_count: int) -> float:
        safe_timeout_seconds = max(1, timeout_seconds)
        safe_retry_count = max(0, retry_count)
        attempt_count = safe_retry_count + 1
        return float(safe_timeout_seconds * attempt_count) + 1.0


    def _request_chat_completion(
        self,
        base_url: str,
        api_key: str,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        normalized_base_url = base_url.rstrip("/")
        request_url = f"{normalized_base_url}/chat/completions"
        return self._request_json(
            url=request_url,
            method="POST",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            payload=payload,
        )


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
        normalized_base_url = configured_base_url.strip().rstrip("/")
        if normalized_base_url == "":
            return []

        parsed_base_url = urllib_parse.urlsplit(normalized_base_url)
        raw_candidates = [normalized_base_url]
        if parsed_base_url.scheme != "" and parsed_base_url.hostname is not None:
            fallback_hosts = ("127.0.0.1", "localhost")
            for fallback_host in fallback_hosts:
                if fallback_host == parsed_base_url.hostname:
                    continue
                fallback_netloc = fallback_host
                if parsed_base_url.port is not None:
                    fallback_netloc = f"{fallback_host}:{parsed_base_url.port}"
                fallback_url = urllib_parse.urlunsplit(
                    (
                        parsed_base_url.scheme,
                        fallback_netloc,
                        parsed_base_url.path,
                        parsed_base_url.query,
                        parsed_base_url.fragment,
                    )
                )
                raw_candidates.append(fallback_url)

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
