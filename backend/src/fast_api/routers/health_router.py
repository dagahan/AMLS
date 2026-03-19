from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from src.models.pydantic import HealthResponse
from src.valkey.valkey_client import get_valkey_client

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_health_router(db: "DataBase") -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])
    valkey_client = get_valkey_client()


    @router.get("", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        database_status = "healthy" if await db.test_connection() else "unhealthy"
        try:
            valkey_status = "healthy" if valkey_client.ping() else "unhealthy"
        except Exception:
            valkey_status = "unhealthy"

        overall_status = "healthy" if database_status == "healthy" and valkey_status == "healthy" else "unhealthy"
        return HealthResponse(
            status=overall_status,
            services={
                "database": database_status,
                "valkey": valkey_status,
            },
        )


    return router
