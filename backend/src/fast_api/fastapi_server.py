from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
import uuid

import uvicorn
from fastapi import FastAPI, Request, Response

from src.config import get_app_config, get_config_manager
from src.core.logging import bind_context, clear_context, get_logger
from src.fast_api.routers.auth_router import get_auth_router
from src.fast_api.routers.course_graph_router import get_course_graph_router
from src.fast_api.routers.course_router import get_course_router
from src.fast_api.routers.difficulty_router import get_difficulty_router
from src.fast_api.routers.health_router import get_health_router
from src.fast_api.routers.lecture_router import get_lecture_router
from src.fast_api.routers.problem_router import get_problem_router
from src.fast_api.routers.problem_type_router import get_problem_type_router
from src.fast_api.routers.storage_router import get_storage_router
from src.fast_api.routers.test_router import get_test_router
from src.fast_api.routers.topic_router import get_topic_router
from src.storage.storage_manager import StorageManager

logger = get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]


def create_application(storage_manager: StorageManager) -> FastAPI:
    app = FastAPI(
        title="Adaptive Mathematics Learning System",
        description="AMLS backend for graph-based adaptive mathematics learning",
        version="0.1.0",
    )
    app.state.storage = storage_manager
    app.middleware("http")(_bind_request_context)
    app.include_router(get_health_router(storage_manager))
    app.include_router(get_auth_router(storage_manager))
    app.include_router(get_course_router(storage_manager))
    app.include_router(get_course_graph_router(storage_manager))
    app.include_router(get_lecture_router(storage_manager))
    app.include_router(get_test_router(storage_manager))
    app.include_router(get_difficulty_router(storage_manager))
    app.include_router(get_topic_router(storage_manager))
    app.include_router(get_problem_type_router(storage_manager))
    app.include_router(get_problem_router(storage_manager))
    app.include_router(get_storage_router(storage_manager))
    return app


async def _bind_request_context(request: Request, call_next: RequestHandler) -> Response:
    clear_context()

    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    bind_context(
        request_id=request_id,
        http_method=request.method,
        http_path=request.url.path,
        client_ip=request.client.host if request.client is not None else None,
    )

    start_time = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - start_time) * 1000, 2)
        logger.exception("Request failed", duration_ms=duration_ms)
        clear_context()
        raise

    response.headers["x-request-id"] = request_id
    duration_ms = round((perf_counter() - start_time) * 1000, 2)
    logger.info(
        "Request completed",
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    clear_context()
    return response


class Server:
    def __init__(self) -> None:
        app_config = get_app_config()
        self.storage_manager = StorageManager()
        self.app = create_application(self.storage_manager)
        self.server: uvicorn.Server | None = None
        self.uvicorn_config = uvicorn.Config(
            app=self.app,
            host=app_config.backend_bind_host(),
            port=app_config.infra.backend_port,
            log_level=app_config.infra.log_level_name.lower(),
            log_config=None,
            access_log=app_config.infra.access_logs_enabled,
        )


    async def run_server(self) -> None:
        await self.storage_manager.connect()
        await get_config_manager().start_watcher()
        self.server = uvicorn.Server(self.uvicorn_config)
        logger.info(
            "Starting FastAPI server",
            app_title=self.app.title,
            host=self.uvicorn_config.host,
            port=self.uvicorn_config.port,
        )
        await self.server.serve()


    async def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True

        await get_config_manager().stop_watcher()
        await self.storage_manager.close()
