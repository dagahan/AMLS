from __future__ import annotations

from enum import StrEnum

from src.models.pydantic.common import AmlsSchema


class LlmRuntimeName(StrEnum):
    LMS_STUDIO = "lms_studio"


class LlmModelDefinition(AmlsSchema):
    model_name: str
    model_base_url: str
    model_api_key_env: str
    model_runtime_name: LlmRuntimeName


class LlmRegistryConfig(AmlsSchema):
    default_model_key: str
    models: dict[str, LlmModelDefinition]


class LlmChatMessage(AmlsSchema):
    role: str
    content: str


class LlmChatCompletionRequest(AmlsSchema):
    messages: list[LlmChatMessage]
    temperature: float


class LlmCompletionResult(AmlsSchema):
    model_name: str
    base_url: str
    completion_text: str
