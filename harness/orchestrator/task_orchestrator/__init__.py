"""Task Orchestrator — Plan-and-Execute con paralelismo DAG (async).

Paquete resultante de la extracción mecánica de
``harness/orchestrator/task_orchestrator.py`` (644 líneas, regla AGR <500):

- ``retry.py``: TypeVar ``F`` + decorador ``async_retry`` (backoff exponencial).
- ``broadcasting.py``: mixin ``_BroadcastingMixin`` (broadcasts async vía asyncio.gather).
- ``orchestrator.py``: clase ``TaskOrchestrator`` (pipeline Plan-and-Execute async).
- ``helpers.py``: ``enable_cache``, ``enable_golden_signals``,
  ``enable_speculative_tools`` y ``run_process_message`` (Composition Root).

Este ``__init__.py`` re-exporta la MISMA superficie de nombres a nivel de
módulo que el módulo original (clases, funciones, constantes y nombres
importados accesibles vía ``from harness.orchestrator.task_orchestrator
import X``) para mantener backward-compat idéntico:

    from harness.orchestrator.task_orchestrator import TaskOrchestrator
    from harness.orchestrator.task_orchestrator import enable_cache, CircuitBreaker
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from harness.orchestrator.agent_bus import AgentBus
from harness.orchestrator.confidence_scorer import ConfidenceScore, ConfidenceScorer
from harness.orchestrator.debate_orchestrator import DebateResult
from harness.orchestrator.orchestration_result import OrchestratorResult
from harness.orchestrator.self_healing import CircuitBreaker, SelfHealingContext
from harness.orchestrator.session_context import SessionContext, SessionState
from harness.orchestrator.structured_log import StructuredLogRecord
from harness.orchestrator.task_planner import TaskPlan, TaskPlanner

logger = logging.getLogger(__name__)

from .helpers import (
    enable_cache,
    enable_golden_signals,
    enable_speculative_tools,
    run_process_message,
)
from .orchestrator import TaskOrchestrator
from .retry import F, async_retry

__all__ = [
    "AgentBus",
    "Any",
    "Callable",
    "CircuitBreaker",
    "ConfidenceScore",
    "ConfidenceScorer",
    "DebateResult",
    "F",
    "OrchestratorResult",
    "SelfHealingContext",
    "SessionContext",
    "SessionState",
    "StructuredLogRecord",
    "TaskOrchestrator",
    "TaskPlan",
    "TaskPlanner",
    "TypeVar",
    "async_retry",
    "asyncio",
    "enable_cache",
    "enable_golden_signals",
    "enable_speculative_tools",
    "functools",
    "hashlib",
    "logger",
    "logging",
    "run_process_message",
    "time",
]
