from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.core.logging import get_logger

P = ParamSpec("P")
T = TypeVar("T")
UndoAction = Callable[[], Awaitable[None]]
DoAction = Callable[[], Awaitable[T]]
UndoWithResult = Callable[[T], Awaitable[None]]

logger = get_logger(__name__)

_current_transaction: ContextVar["TransactionRecorder | None"] = ContextVar(
    "_current_transaction",
    default=None,
)


class TransactionRecorder(BaseModel):
    model_config = ConfigDict()

    rollback_actions: list[UndoAction] = Field(default_factory=list)
    completed_steps: int = 0
    step_times: dict[str, float] = Field(default_factory=dict)
    step_starts: dict[str, float] = Field(default_factory=dict)


    def register_rollback(self, action: UndoAction) -> None:
        self.rollback_actions.append(action)
        self.completed_steps += 1


    def start_step_timer(self, step_name: str) -> None:
        self.step_starts[step_name] = perf_counter()


    def end_step_timer(self, step_name: str) -> None:
        if step_name in self.step_starts:
            duration_ms = (perf_counter() - self.step_starts[step_name]) * 1000
            self.step_times[step_name] = duration_ms
            logger.info(
                "Transaction step completed",
                step_name=step_name,
                duration_ms=round(duration_ms, 2),
            )
            del self.step_starts[step_name]


    async def rollback_all(self) -> None:
        while self.rollback_actions:
            action = self.rollback_actions.pop()
            try:
                await action()
            except Exception as error:
                logger.exception("Rollback action failed", error=str(error))


@asynccontextmanager
async def transaction_scope() -> Any:
    recorder = TransactionRecorder()
    token = _current_transaction.set(recorder)
    try:
        yield
    except Exception as error:
        logger.exception(
            "Transaction failed",
            completed_steps=recorder.completed_steps,
            error=str(error),
        )
        await recorder.rollback_all()
        raise
    finally:
        _current_transaction.reset(token)


def transactional(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        async with transaction_scope():
            return await func(*args, **kwargs)

    return wrapper


async def execute_atomic_step(
    action: DoAction[T],
    rollback: UndoWithResult[T] | None = None,
    step_name: str | None = None,
) -> T:
    recorder = _current_transaction.get()
    if recorder is None:
        raise RuntimeError("execute_atomic_step must be used within @transactional function")

    if step_name:
        recorder.start_step_timer(step_name)

    try:
        result = await action()

        if step_name:
            recorder.end_step_timer(step_name)

        if rollback is not None:
            async def rollback_action() -> None:
                try:
                    await rollback(result)
                except Exception as error:
                    logger.exception("Rollback failed", step_name=step_name, error=str(error))
                    raise

            recorder.register_rollback(rollback_action)

        return result
    
    except Exception:
        if step_name:
            recorder.end_step_timer(step_name)
        raise
