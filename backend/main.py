import asyncio
import signal
import sys

import colorama
from loguru import logger

from src.core.logging import InterceptHandler, LogSetup
from src.core.utils import EnvTools
from src.fast_api.fastapi_server import Server


class Service:
    def __init__(self) -> None:
        self.intercept_handler = InterceptHandler()
        self.logger_setup = LogSetup()
        self.fastapi_server = Server()


    async def run_service(self) -> None:
        self.logger_setup.configure()

        loop = asyncio.get_running_loop()
        stop_future: asyncio.Future[None] = loop.create_future()

        for current_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    current_signal,
                    lambda current_signal=current_signal: (
                        not stop_future.done()
                    ) and stop_future.set_result(None),
                )
            except NotImplementedError:
                continue

        server_task = asyncio.create_task(
            self.fastapi_server.run_server(),
            name="FastAPI-Thesis",
        )

        pending_tasks: set[asyncio.Future[None]] = {server_task, stop_future}

        try:
            finished_tasks, pending_tasks = await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in finished_tasks:
                if task is stop_future:
                    logger.info(
                        f"{colorama.Fore.YELLOW}Shutdown signal received{colorama.Style.RESET_ALL}"
                    )
                elif isinstance(task, asyncio.Task) and task.exception():
                    logger.error(
                        f"{colorama.Fore.RED}{task.get_name()} crashed: {task.exception()}{colorama.Style.RESET_ALL}"
                    )
        except asyncio.CancelledError:
            logger.info(
                f"{colorama.Fore.YELLOW}Service stop requested{colorama.Style.RESET_ALL}"
            )
        finally:
            await self.fastapi_server.stop()

            for task in pending_tasks:
                if not isinstance(task, asyncio.Task):
                    continue

                if task.get_name() == "FastAPI-Thesis":
                    await task
                    continue

                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    continue

            logger.info(
                f"{colorama.Fore.GREEN}FastAPI server stopped gracefully{colorama.Style.RESET_ALL}"
            )


if __name__ == "__main__":
    try:
        EnvTools.bootstrap_env(service_directory="backend")
        asyncio.run(Service().run_service())
    except KeyboardInterrupt:
        logger.info(f"{colorama.Fore.CYAN}Service stopped by user{colorama.Style.RESET_ALL}")
    except Exception as error:
        logger.critical(f"{colorama.Fore.RED}Service crashed: {error}{colorama.Style.RESET_ALL}")
        sys.exit(1)
