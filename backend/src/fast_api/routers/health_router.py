from __future__ import annotations

from fastapi import APIRouter

from src.models.pydantic import HealthResponse
from src.storage.storage_manager import StorageManager


def get_health_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])


    @router.get("", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        database_status = "healthy" if await storage_manager.check_database() else "unhealthy"
        valkey_status = "healthy" if storage_manager.check_valkey() else "unhealthy"

        overall_status = "healthy" if database_status == "healthy" and valkey_status == "healthy" else "unhealthy"
        return HealthResponse(
            status=overall_status,
            services={
                "database": database_status,
                "valkey": valkey_status,
            },
        )


    return router
