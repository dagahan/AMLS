import json

import pytest

from src.models.pydantic.llm import (
    LlmChatCompletionRequest,
    LlmChatMessage,
    LlmModelDefinition,
    LlmRuntimeName,
)
from src.services.lms_studio_runtime_client import LmsStudioRuntimeClient


def build_model_definition(base_url: str = "http://localhost:1234/v1") -> LlmModelDefinition:
    return LlmModelDefinition(
        model_name="qwen2.5-coder-3b-instruct-mlx",
        model_base_url=base_url,
        model_api_key_env="LMS_API_KEY",
        model_runtime_name=LlmRuntimeName.LMS_STUDIO,
    )


def test_resolve_working_base_url_falls_back_to_local_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LmsStudioRuntimeClient()
    call_urls: list[str] = []

    def request_json(
        *,
        url: str,
        method: str,
        api_key: str,
        timeout_seconds: int,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        call_urls.append(url)
        assert method == "GET"
        assert api_key == "lm-studio"
        assert timeout_seconds == 2
        assert payload is None
        if url.startswith("http://unreachable-host.tailnet:1234/v1/models"):
            raise RuntimeError("HTTP Error 503: Service Unavailable")
        if url.startswith("http://127.0.0.1:1234/v1/models"):
            return {"data": [{"id": "qwen2.5-coder-3b-instruct-mlx"}]}
        raise RuntimeError("Unexpected probe URL")

    monkeypatch.setattr(client, "_request_json", request_json)

    resolved_base_url = client._resolve_working_base_url(
        configured_base_url="http://unreachable-host.tailnet:1234/v1",
        api_key="lm-studio",
        timeout_seconds=2,
    )

    assert resolved_base_url == "http://127.0.0.1:1234/v1"
    assert call_urls == [
        "http://unreachable-host.tailnet:1234/v1/models",
        "http://127.0.0.1:1234/v1/models",
    ]


def test_request_loaded_model_ids_supports_models_payload_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LmsStudioRuntimeClient()

    def request_json(
        *,
        url: str,
        method: str,
        api_key: str,
        timeout_seconds: int,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        assert url == "http://localhost:1234/api/v1/models"
        assert method == "GET"
        assert api_key == "lm-studio"
        assert timeout_seconds == 3
        assert payload is None
        return {
            "models": [
                {
                    "key": "qwen2.5-coder-3b-instruct-mlx",
                    "loaded_instances": [
                        {"id": "qwen2.5-coder-3b-instruct-mlx:2"},
                    ],
                },
                {
                    "key": "qwen/qwen3-8b",
                    "loaded_instances": [],
                },
            ]
        }

    monkeypatch.setattr(client, "_request_json", request_json)

    loaded_model_ids = client._request_loaded_model_ids(
        management_base_url="http://localhost:1234",
        api_key="lm-studio",
        timeout_seconds=3,
    )

    assert "qwen2.5-coder-3b-instruct-mlx" in loaded_model_ids
    assert "qwen2.5-coder-3b-instruct-mlx:2" in loaded_model_ids
    assert client._is_model_loaded(
        requested_model="qwen2.5-coder-3b-instruct-mlx",
        loaded_model_ids=loaded_model_ids,
    ) is True


def test_ensure_model_available_calls_load_until_model_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LmsStudioRuntimeClient()
    call_state = {"model_checks": 0, "load_calls": 0}

    def request_loaded_model_ids(
        *,
        management_base_url: str,
        api_key: str,
        timeout_seconds: int,
    ) -> set[str]:
        assert management_base_url == "http://localhost:1234"
        assert api_key == "lm-studio"
        assert timeout_seconds == 1
        call_state["model_checks"] += 1
        if call_state["model_checks"] == 1:
            return set()
        return {"qwen2.5-coder-3b-instruct-mlx"}

    def request_model_load(
        *,
        management_base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        assert management_base_url == "http://localhost:1234"
        assert api_key == "lm-studio"
        assert model == "qwen2.5-coder-3b-instruct-mlx"
        assert timeout_seconds == 1
        call_state["load_calls"] += 1

    monkeypatch.setattr(client, "_request_loaded_model_ids", request_loaded_model_ids)
    monkeypatch.setattr(client, "_request_model_load", request_model_load)

    client._ensure_model_available(
        base_url="http://localhost:1234/v1",
        api_key="lm-studio",
        model="qwen2.5-coder-3b-instruct-mlx",
        timeout_seconds=1,
        retry_count=1,
    )

    assert call_state["model_checks"] == 2
    assert call_state["load_calls"] == 1


@pytest.mark.asyncio
async def test_create_chat_completion_runs_auto_wake_and_returns_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LmsStudioRuntimeClient()
    call_state = {"wake_calls": 0}

    def resolve_working_base_url(
        *,
        configured_base_url: str,
        api_key: str,
        timeout_seconds: int,
    ) -> str:
        assert configured_base_url == "http://localhost:1234/v1"
        assert api_key == "lm-studio"
        assert timeout_seconds == 3
        return configured_base_url

    def ensure_model_available(**_: object) -> None:
        call_state["wake_calls"] += 1

    def request_chat_completion(
        base_url: str,
        api_key: str,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        assert base_url == "http://localhost:1234/v1"
        assert api_key == "lm-studio"
        assert payload["model"] == "qwen2.5-coder-3b-instruct-mlx"
        assert timeout_seconds == 3
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "recommendations": ["Practice vectors"],
                            }
                        ),
                    }
                }
            ]
        }

    monkeypatch.setattr(client, "_resolve_working_base_url", resolve_working_base_url)
    monkeypatch.setattr(client, "_ensure_model_available", ensure_model_available)
    monkeypatch.setattr(client, "_request_chat_completion", request_chat_completion)

    completion_result = await client.create_chat_completion(
        model_definition=build_model_definition(),
        api_key="lm-studio",
        request=LlmChatCompletionRequest(
            temperature=0.2,
            messages=[
                LlmChatMessage(role="system", content="system"),
                LlmChatMessage(role="user", content="user"),
            ],
        ),
        completion_timeout_seconds=3,
        auto_wake_enabled=True,
        auto_wake_timeout_seconds=1,
        auto_wake_retry_count=1,
    )

    assert call_state["wake_calls"] == 1
    assert completion_result.model_name == "qwen2.5-coder-3b-instruct-mlx"
    assert completion_result.base_url == "http://localhost:1234/v1"
    assert "Practice vectors" in completion_result.completion_text


def test_extract_completion_content_raises_on_malformed_payload() -> None:
    client = LmsStudioRuntimeClient()

    with pytest.raises(RuntimeError, match="choices"):
        client._extract_completion_content({"id": "no-choices"})
