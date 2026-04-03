import json
from dataclasses import dataclass

import pytest

from src.services.graph_assessment.review_generation_service import GraphAssessmentReviewService
from src.storage.db.enums import GraphAssessmentReviewStatus, TestAttemptKind as AttemptKind


@dataclass(slots=True)
class InfraConfigStub:
    lms_base_url: str
    lms_api_key: str
    lms_model: str
    lms_timeout_seconds: int
    lms_auto_wake_enabled: bool
    lms_auto_wake_timeout_seconds: int
    lms_auto_wake_retry_count: int


@dataclass(slots=True)
class AppConfigStub:
    infra: InfraConfigStub


def build_config(auto_wake_enabled: bool) -> AppConfigStub:
    return AppConfigStub(
        infra=InfraConfigStub(
            lms_base_url="http://localhost:1234/v1",
            lms_api_key="lm-studio",
            lms_model="qwen2.5-coder-3b-instruct-mlx",
            lms_timeout_seconds=3,
            lms_auto_wake_enabled=auto_wake_enabled,
            lms_auto_wake_timeout_seconds=1,
            lms_auto_wake_retry_count=1,
        )
    )


@pytest.mark.asyncio
async def test_generate_review_calls_auto_wake_and_returns_success(monkeypatch: pytest.MonkeyPatch) -> None:
    config = build_config(auto_wake_enabled=True)
    service = GraphAssessmentReviewService()
    call_state = {"warmups": 0}

    def ensure_model_available(**_: object) -> None:
        call_state["warmups"] += 1

    def request_chat_completion(_: str, __: str, payload: dict[str, object]) -> dict[str, object]:
        assert payload["model"] == config.infra.lms_model
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "review_text": "Strong baseline. Continue with vector tasks.",
                                "recommendations": ["Practice vectors", "Review fractions"],
                            }
                        ),
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "src.services.graph_assessment.review_generation_service.get_app_config",
        lambda: config,
    )
    monkeypatch.setattr(service, "_ensure_model_available", ensure_model_available)
    monkeypatch.setattr(service, "_request_chat_completion", request_chat_completion)

    generated_review = await service.generate_review(
        course_title="Profile Mathematics (Grades 10-11)",
        assessment_kind=AttemptKind.ENTRANCE,
        state_confidence=0.72,
        learned_count=20,
        ready_count=14,
        locked_count=8,
        failed_count=3,
    )

    assert call_state["warmups"] == 1
    assert generated_review.status == GraphAssessmentReviewStatus.SUCCEEDED
    assert generated_review.review_text == "Strong baseline. Continue with vector tasks."
    assert generated_review.review_recommendations == ["Practice vectors", "Review fractions"]
    assert generated_review.review_error is None
    assert generated_review.generated_at is not None


@pytest.mark.asyncio
async def test_generate_review_keeps_completion_path_when_auto_wake_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = build_config(auto_wake_enabled=True)
    service = GraphAssessmentReviewService()
    call_state = {"warmups": 0}

    def ensure_model_available(**_: object) -> None:
        call_state["warmups"] += 1
        raise RuntimeError("Warm-up endpoint unavailable")

    def request_chat_completion(_: str, __: str, ___: dict[str, object]) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "review_text": "Fallback still generated through chat completion.",
                                "recommendations": ["Retry difficult nodes"],
                            }
                        ),
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "src.services.graph_assessment.review_generation_service.get_app_config",
        lambda: config,
    )
    monkeypatch.setattr(service, "_ensure_model_available", ensure_model_available)
    monkeypatch.setattr(service, "_request_chat_completion", request_chat_completion)

    generated_review = await service.generate_review(
        course_title="Profile Mathematics (Grades 10-11)",
        assessment_kind=AttemptKind.GENERAL,
        state_confidence=0.61,
        learned_count=18,
        ready_count=10,
        locked_count=12,
        failed_count=5,
    )

    assert call_state["warmups"] == 1
    assert generated_review.status == GraphAssessmentReviewStatus.SUCCEEDED
    assert generated_review.review_text == "Fallback still generated through chat completion."
    assert generated_review.review_recommendations == ["Retry difficult nodes"]
    assert generated_review.review_error is None


@pytest.mark.asyncio
async def test_generate_review_returns_failed_status_when_completion_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = build_config(auto_wake_enabled=False)
    service = GraphAssessmentReviewService()

    def request_chat_completion(_: str, __: str, ___: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("LM Studio completion failed")

    monkeypatch.setattr(
        "src.services.graph_assessment.review_generation_service.get_app_config",
        lambda: config,
    )
    monkeypatch.setattr(service, "_request_chat_completion", request_chat_completion)

    generated_review = await service.generate_review(
        course_title="Profile Mathematics (Grades 10-11)",
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
    assert generated_review.review_error == "LM Studio completion failed"
    assert generated_review.generated_at is None


def test_resolve_working_base_url_falls_back_to_local_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GraphAssessmentReviewService()
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

    monkeypatch.setattr(service, "_request_json", request_json)

    resolved_base_url = service._resolve_working_base_url(
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
    service = GraphAssessmentReviewService()

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

    monkeypatch.setattr(service, "_request_json", request_json)

    loaded_model_ids = service._request_loaded_model_ids(
        management_base_url="http://localhost:1234",
        api_key="lm-studio",
        timeout_seconds=3,
    )

    assert "qwen2.5-coder-3b-instruct-mlx" in loaded_model_ids
    assert "qwen2.5-coder-3b-instruct-mlx:2" in loaded_model_ids
    assert service._is_model_loaded(
        requested_model="qwen2.5-coder-3b-instruct-mlx",
        loaded_model_ids=loaded_model_ids,
    ) is True
