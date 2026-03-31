from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.core.logging import bind_context, clear_context, get_context

if TYPE_CHECKING:
    from httpx import AsyncClient


def test_logging_context_round_trip() -> None:
    clear_context()
    bind_context(request_id="request-123", user_id="user-123")

    context = get_context()

    assert context["request_id"] == "request-123"
    assert context["user_id"] == "user-123"

    clear_context()
    assert get_context() == {}


@pytest.mark.asyncio
async def test_request_id_header_is_preserved(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"x-request-id": "request-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "request-123"


@pytest.mark.asyncio
async def test_request_id_header_is_generated_for_error_response(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["x-request-id"]
