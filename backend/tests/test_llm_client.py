from __future__ import annotations

from typing import Any, cast

import pytest

from src.models.pydantic.llm import (
    LlmChatCompletionRequest,
    LlmChatMessage,
    LlmCompletionResult,
    LlmModelDefinition,
    LlmRegistryConfig,
    LlmRuntimeName,
)
from src.services.llm_client import LlmClient


class InfraConfigStub:
    def __init__(
        self,
        *,
        lms_timeout_seconds: int,
        lms_auto_wake_enabled: bool,
        lms_auto_wake_timeout_seconds: int,
        lms_auto_wake_retry_count: int,
    ) -> None:
        self.lms_timeout_seconds = lms_timeout_seconds
        self.lms_auto_wake_enabled = lms_auto_wake_enabled
        self.lms_auto_wake_timeout_seconds = lms_auto_wake_timeout_seconds
        self.lms_auto_wake_retry_count = lms_auto_wake_retry_count


class BusinessConfigStub:
    def __init__(self, *, llm_registry: LlmRegistryConfig) -> None:
        self.llm_registry = llm_registry


class AppConfigStub:
    def __init__(
        self,
        *,
        infra: InfraConfigStub,
        business: BusinessConfigStub,
        environment_values: dict[str, str],
    ) -> None:
        self.infra = infra
        self.business = business
        self.environment_values = environment_values


class RuntimeClientStub:
    def __init__(self, completion_result: LlmCompletionResult) -> None:
        self.completion_result = completion_result
        self.call_count = 0
        self.last_model_definition: LlmModelDefinition | None = None
        self.last_api_key: str | None = None
        self.last_request: LlmChatCompletionRequest | None = None


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
        assert completion_timeout_seconds == 3
        assert auto_wake_enabled is True
        assert auto_wake_timeout_seconds == 1
        assert auto_wake_retry_count == 2
        self.call_count += 1
        self.last_model_definition = model_definition
        self.last_api_key = api_key
        self.last_request = request
        return self.completion_result


def build_registry() -> LlmRegistryConfig:
    return LlmRegistryConfig(
        default_model_key="local_qwen",
        models={
            "local_qwen": LlmModelDefinition(
                model_name="qwen2.5-coder-3b-instruct-mlx",
                model_base_url="http://127.0.0.1:1234/v1",
                model_api_key_env="LMS_API_KEY",
                model_runtime_name=LlmRuntimeName.LMS_STUDIO,
            )
        },
    )


def build_app_config(
    *,
    llm_registry: LlmRegistryConfig,
    environment_values: dict[str, str],
) -> AppConfigStub:
    return AppConfigStub(
        infra=InfraConfigStub(
            lms_timeout_seconds=3,
            lms_auto_wake_enabled=True,
            lms_auto_wake_timeout_seconds=1,
            lms_auto_wake_retry_count=2,
        ),
        business=BusinessConfigStub(llm_registry=llm_registry),
        environment_values=environment_values,
    )


@pytest.mark.asyncio
async def test_create_chat_completion_dispatches_by_runtime_and_model_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RuntimeClientStub(
        completion_result=LlmCompletionResult(
            model_name="qwen2.5-coder-3b-instruct-mlx",
            base_url="http://127.0.0.1:1234/v1",
            completion_text="{\"recommendations\":[\"Practice vectors\"]}",
        )
    )
    llm_client = LlmClient(lms_studio_runtime_client=runtime_client)
    app_config = build_app_config(
        llm_registry=build_registry(),
        environment_values={"LMS_API_KEY": "lm-studio"},
    )
    monkeypatch.setattr("src.services.llm_client.get_app_config", lambda: app_config)

    completion_result = await llm_client.create_chat_completion(
        request=LlmChatCompletionRequest(
            temperature=0.2,
            messages=[
                LlmChatMessage(role="system", content="system"),
                LlmChatMessage(role="user", content="user"),
            ],
        ),
        model_key=None,
    )

    assert runtime_client.call_count == 1
    assert runtime_client.last_model_definition is not None
    assert runtime_client.last_model_definition.model_name == "qwen2.5-coder-3b-instruct-mlx"
    assert runtime_client.last_api_key == "lm-studio"
    assert runtime_client.last_request is not None
    assert completion_result.model_name == "qwen2.5-coder-3b-instruct-mlx"


@pytest.mark.asyncio
async def test_create_chat_completion_fails_when_default_model_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RuntimeClientStub(
        completion_result=LlmCompletionResult(
            model_name="unused",
            base_url="http://127.0.0.1:1234/v1",
            completion_text="unused",
        )
    )
    llm_client = LlmClient(lms_studio_runtime_client=runtime_client)
    broken_registry = LlmRegistryConfig(
        default_model_key="missing_model",
        models={},
    )
    app_config = build_app_config(
        llm_registry=broken_registry,
        environment_values={"LMS_API_KEY": "lm-studio"},
    )
    monkeypatch.setattr("src.services.llm_client.get_app_config", lambda: app_config)

    with pytest.raises(RuntimeError, match="not configured"):
        await llm_client.create_chat_completion(
            request=LlmChatCompletionRequest(
                temperature=0.2,
                messages=[LlmChatMessage(role="user", content="user")],
            ),
        )


@pytest.mark.asyncio
async def test_create_chat_completion_fails_when_runtime_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RuntimeClientStub(
        completion_result=LlmCompletionResult(
            model_name="unused",
            base_url="http://127.0.0.1:1234/v1",
            completion_text="unused",
        )
    )
    llm_client = LlmClient(lms_studio_runtime_client=runtime_client)
    broken_model_definition = LlmModelDefinition.model_construct(
        model_name="unknown-runtime-model",
        model_base_url="http://127.0.0.1:1234/v1",
        model_api_key_env="LMS_API_KEY",
        model_runtime_name=cast("Any", "unknown_runtime"),
    )
    broken_registry = LlmRegistryConfig.model_construct(
        default_model_key="broken_model",
        models={"broken_model": broken_model_definition},
    )
    app_config = build_app_config(
        llm_registry=broken_registry,
        environment_values={"LMS_API_KEY": "lm-studio"},
    )
    monkeypatch.setattr("src.services.llm_client.get_app_config", lambda: app_config)

    with pytest.raises(RuntimeError, match="not supported"):
        await llm_client.create_chat_completion(
            request=LlmChatCompletionRequest(
                temperature=0.2,
                messages=[LlmChatMessage(role="user", content="user")],
            ),
        )


@pytest.mark.asyncio
async def test_create_chat_completion_fails_when_model_api_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RuntimeClientStub(
        completion_result=LlmCompletionResult(
            model_name="unused",
            base_url="http://127.0.0.1:1234/v1",
            completion_text="unused",
        )
    )
    llm_client = LlmClient(lms_studio_runtime_client=runtime_client)
    app_config = build_app_config(
        llm_registry=build_registry(),
        environment_values={},
    )
    monkeypatch.setattr("src.services.llm_client.get_app_config", lambda: app_config)

    with pytest.raises(RuntimeError, match="missing in environment values"):
        await llm_client.create_chat_completion(
            request=LlmChatCompletionRequest(
                temperature=0.2,
                messages=[LlmChatMessage(role="user", content="user")],
            ),
        )
