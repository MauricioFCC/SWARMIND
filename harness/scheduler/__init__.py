"""Unified scheduler — BaseScheduler ABC + JobStore mixin + concrete implementations.

Paquete resultante de la extracción mecánica de ``harness/scheduler.py``
(811 líneas, regla AGR <500). Estructura:

- ``scheduled_job.py``: dataclass ``ScheduledJob`` (schemas Simple/Lance unificados).
- ``base.py``: ABC ``BaseScheduler`` (add_job, remove_job, list_jobs, get_job, stop).
- ``job_store.py``: mixin ``JobStore`` (persistencia JSON/YAML auto-detectada).
- ``simple.py``: ``SimpleScheduler`` (cron + persistencia JSON).
- ``lance.py``: ``LanceScheduler`` (schedule-lib + YAML + logging LanceDB).

Este ``__init__.py`` re-exporta TODOS los símbolos públicos del módulo
original (incluido el estado de módulo que los tests parchean: ``logger``,
``croniter``, ``HAS_CRONITER``, ``EMBEDDING_DIM``, ``time``) para mantener
backward-compat idéntico:

    from harness.scheduler import SimpleScheduler, TaskScheduler
    patch("harness.scheduler.logger")
    patch("harness.scheduler.croniter", ...)

Los submódulos acceden al estado compartido vía
``import harness.scheduler as _pkg`` en tiempo de llamada, de modo que
``unittest.mock.patch`` sobre el paquete siga funcionando igual que con el
módulo plano original.

Aliases backward-compat:
- ``TaskScheduler``: alias de ``SimpleScheduler`` (nombre del módulo original).
- ``Scheduler``: alias de ``LanceScheduler`` (nombre de orchestrator/scheduler.py).
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar

try:
    from croniter import croniter  # type: ignore[import-untyped]  # noqa: F401 — re-export condicional via __all__
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

EMBEDDING_DIM = 384

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths (mismo directorio que el módulo original: harness/)
# ---------------------------------------------------------------------------

_HARNESS_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_SIMPLE_JOBS_PATH = str(_HARNESS_ROOT / "scheduler_jobs.json")
_DEFAULT_LANCE_JOBS_PATH = str(
    _HARNESS_ROOT / "orchestrator" / "scheduler_jobs.yaml",
)


# ---------------------------------------------------------------------------
# Submódulos (re-export backward-compat)
# ---------------------------------------------------------------------------

from .base import BaseScheduler
from .job_store import JobStore
from .lance import LanceScheduler
from .scheduled_job import ScheduledJob
from .simple import SimpleScheduler

# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

#: Alias for :class:`SimpleScheduler` — the name used in the original
#: ``harness/scheduler.py`` module.
TaskScheduler = SimpleScheduler

#: Alias for :class:`LanceScheduler` — the name used in the original
#: ``harness/orchestrator/scheduler.py`` module.
Scheduler = LanceScheduler

__all__ = [
    "ABC",
    "EMBEDDING_DIM",
    "HAS_CRONITER",
    "Any",
    "BaseScheduler",
    "ClassVar",
    "JobStore",
    "LanceScheduler",
    "Path",
    "ScheduledJob",
    "Scheduler",
    "SimpleScheduler",
    "TaskScheduler",
    "abstractmethod",
    "asdict",
    "dataclass",
    "datetime",
    "json",
    "logger",
    "logging",
    "threading",
    "time",
]

# ``croniter`` solo existe cuando el paquete opcional está instalado
# (mismo comportamiento que el módulo plano original).
if HAS_CRONITER:
    __all__.append("croniter")
