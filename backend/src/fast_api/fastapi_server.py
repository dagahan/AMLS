from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src.config import get_app_config, get_config_manager
from src.fast_api.routers.auth_router import get_auth_router
from src.fast_api.routers.difficulty_router import get_difficulty_router
from src.fast_api.routers.entrance_test_router import get_entrance_test_router
from src.fast_api.routers.health_router import get_health_router
from src.fast_api.routers.problem_router import get_problem_router
from src.fast_api.routers.problem_type_router import get_problem_type_router
from src.fast_api.routers.storage_router import get_storage_router
from src.fast_api.routers.topic_router import get_topic_router
from src.storage.storage_manager import StorageManager


def create_application(storage_manager: StorageManager) -> FastAPI:
    app = FastAPI(
        title="Adaptive Mathematics Learning System",
        description="AMLS backend for graph-based adaptive mathematics learning",
        version="0.1.0",
    )
    app.state.storage = storage_manager
    app.include_router(get_health_router(storage_manager))
    app.include_router(get_auth_router(storage_manager))
    app.include_router(get_entrance_test_router(storage_manager))
    app.include_router(get_difficulty_router(storage_manager))
    app.include_router(get_topic_router(storage_manager))
    app.include_router(get_problem_type_router(storage_manager))
    app.include_router(get_problem_router(storage_manager))
    app.include_router(get_storage_router(storage_manager))
    return app


class Server:
    def __init__(self) -> None:
        app_config = get_app_config()
        self.storage_manager = StorageManager()
        self.app = create_application(self.storage_manager)
        self.server: uvicorn.Server | None = None
        self.uvicorn_config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0"
            if app_config.is_running_inside_docker()
            else app_config.service_host("backend"),
            port=app_config.service_port("backend"),
            log_level="info",
        )


    async def run_server(self) -> None:
        await self.storage_manager.connect()
        await get_config_manager().start_watcher()
        self.server = uvicorn.Server(self.uvicorn_config)
        logger.info(f"Starting {self.app.title} FastAPI server")
        await self.server.serve()


    async def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True

        await get_config_manager().stop_watcher()
        await self.storage_manager.close()
