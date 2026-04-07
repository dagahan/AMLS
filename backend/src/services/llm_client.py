from __future__ import annotations

from typing import Protocol

from src.config import AppConfig, get_app_config
from src.core.logging import get_logger
from src.models.pydantic.llm import (
    LlmChatCompletionRequest,
    LlmCompletionResult,
    LlmModelDefinition,
    LlmRuntimeName,
)
from src.services.lms_studio_runtime_client import LmsStudioRuntimeClient


logger = get_logger(__name__)


class RuntimeClientProtocol(Protocol):
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
        ...


class LlmClient:
    def __init__(
        self,
        lms_studio_runtime_client: RuntimeClientProtocol | None = None,
    ) -> None:
        runtime_client = lms_studio_runtime_client or LmsStudioRuntimeClient()
        self._runtime_clients: dict[LlmRuntimeName, RuntimeClientProtocol] = {
            LlmRuntimeName.LMS_STUDIO: runtime_client,
        }


    async def create_chat_completion(
        self,
        *,
        request: LlmChatCompletionRequest,
        model_key: str | None = None,
    ) -> LlmCompletionResult:
        app_config = get_app_config()
        llm_registry = app_config.business.llm_registry
        selected_model_key = model_key if model_key is not None else llm_registry.default_model_key
        model_definition = llm_registry.models.get(selected_model_key)
        if model_definition is None:
            raise RuntimeError(f"LLM model key '{selected_model_key}' is not configured")

        runtime_client = self._runtime_clients.get(model_definition.model_runtime_name)
        if runtime_client is None:
            raise RuntimeError(
                f"LLM runtime '{model_definition.model_runtime_name}' is not supported"
            )

        api_key = self._resolve_model_api_key(
            app_config=app_config,
            model_definition=model_definition,
            model_key=selected_model_key,
        )
        logger.info(
            "Dispatching chat completion request",
            model_key=selected_model_key,
            model_name=model_definition.model_name,
            runtime=model_definition.model_runtime_name.value,
        )
        return await runtime_client.create_chat_completion(
            model_definition=model_definition,
            api_key=api_key,
            request=request,
            completion_timeout_seconds=app_config.infra.lms_timeout_seconds,
            auto_wake_enabled=app_config.infra.lms_auto_wake_enabled,
            auto_wake_timeout_seconds=app_config.infra.lms_auto_wake_timeout_seconds,
            auto_wake_retry_count=app_config.infra.lms_auto_wake_retry_count,
        )


    def _resolve_model_api_key(
        self,
        *,
        app_config: AppConfig,
        model_definition: LlmModelDefinition,
        model_key: str,
    ) -> str:
        api_key = app_config.environment_values.get(model_definition.model_api_key_env)
        if api_key is None:
            raise RuntimeError(
                "LLM API key is missing in environment values: "
                f"model_key='{model_key}', env_key='{model_definition.model_api_key_env}'"
            )
        normalized_api_key = api_key.strip()
        if normalized_api_key == "":
            raise RuntimeError(
                "LLM API key is empty in environment values: "
                f"model_key='{model_key}', env_key='{model_definition.model_api_key_env}'"
            )
        return normalized_api_key
