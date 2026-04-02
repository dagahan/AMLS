import asyncio
import signal
import sys

from src.config import bootstrap_config, get_app_config
from src.core.logging import get_logger
from src.fast_api.fastapi_server import Server

logger = get_logger(__name__)


class Service:
    def __init__(self) -> None:
        self.fastapi_server = Server()


    async def run_service(self) -> None:
        loop = asyncio.get_running_loop()
        stop_future: asyncio.Future[None] = loop.create_future()

        for current_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                def request_stop() -> None:
                    if not stop_future.done():
                        stop_future.set_result(None)

                loop.add_signal_handler(
                    current_signal,
                    request_stop,
                )
            except NotImplementedError:
                continue

        server_task = asyncio.create_task(
            self.fastapi_server.run_server(),
            name="FastAPI-AMLS",
        )

        pending_tasks: set[asyncio.Future[None]] = {server_task, stop_future}

        try:
            finished_tasks, pending_tasks = await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in finished_tasks:
                if task is stop_future:
                    logger.info("Shutdown signal received")
                elif isinstance(task, asyncio.Task) and task.exception():
                    logger.error(
                        "Background task crashed",
                        task_name=task.get_name(),
                        error=str(task.exception()),
                    )
        except asyncio.CancelledError:
            logger.info("Service stop requested")
        finally:
            await self.fastapi_server.stop()

            for task in pending_tasks:
                if not isinstance(task, asyncio.Task):
                    continue

                if task.get_name() == "FastAPI-AMLS":
                    await task
                    continue

                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    continue

            logger.info("FastAPI server stopped gracefully")


if __name__ == "__main__":
    try:
        bootstrap_config()
        asyncio.run(Service().run_service())
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as error:
        try:
            time_zone = get_app_config().infra.time_zone_name
        except RuntimeError:
            time_zone = "UTC"
        logger.exception(
            "Service crashed",
            error=str(error),
            time_zone=time_zone,
        )
        sys.exit(1)
