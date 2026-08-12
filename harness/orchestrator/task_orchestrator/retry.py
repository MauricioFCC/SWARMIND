"""Decorador ``async_retry`` — reintentos async con backoff exponencial.

Extracción mecánica desde ``harness/orchestrator/task_orchestrator.py``
(sin cambios de lógica).
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

from harness.orchestrator.structured_log import StructuredLogRecord

F = TypeVar("F", bound=Callable[..., Any])


def async_retry(
    max_retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable[[F], F]:
    """Reintenta operaciones async con backoff exponencial."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1 + max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = backoff * (2 ** attempt)
                        StructuredLogRecord.warning(
                            "async_retry",
                            message=f"Reintentando {func.__name__} "
                                    f"(intento {attempt+1}/{max_retries+1}): {exc}",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay_sec=round(wait, 2),
                        )
                        await asyncio.sleep(wait)
            raise AssertionError("Unreachable") from last_exc
        return wrapper  # type: ignore[return-value]
    return decorator
