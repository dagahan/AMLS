from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src.core.utils import EnvTools
from src.db.database import DataBase
from src.fast_api.routers.auth_router import get_auth_router
from src.fast_api.routers.difficulty_router import get_difficulty_router
from src.fast_api.routers.health_router import get_health_router
from src.fast_api.routers.problem_router import get_problem_router
from src.fast_api.routers.skill_router import get_skill_router
from src.fast_api.routers.storage_router import get_storage_router
from src.fast_api.routers.topic_router import get_topic_router


def create_application(database: DataBase) -> FastAPI:
    app = FastAPI(
        title="Adaptive Mathematics Learning System",
        description="AMLS backend for graph-based adaptive mathematics learning",
        version="0.1.0",
    )
    app.state.database = database
    app.include_router(get_health_router(database))
    app.include_router(get_auth_router(database))
    app.include_router(get_difficulty_router(database))
    app.include_router(get_topic_router(database))
    app.include_router(get_skill_router(database))
    app.include_router(get_problem_router(database))
    app.include_router(get_storage_router(database))
    return app


class Server:
    def __init__(self) -> None:
        self.database = DataBase()
        self.app = create_application(self.database)
        self.server: uvicorn.Server | None = None
        self.uvicorn_config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0"
            if EnvTools.is_running_inside_docker_compose()
            else EnvTools.get_service_host("backend"),
            port=int(EnvTools.get_service_port("backend")),
            log_level="info",
        )


    async def run_server(self) -> None:
        await self.database.init_alchemy_engine()
        self.server = uvicorn.Server(self.uvicorn_config)
        logger.info(f"Starting {self.app.title} FastAPI server")
        await self.server.serve()


    async def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True

        await self.database.dispose()
