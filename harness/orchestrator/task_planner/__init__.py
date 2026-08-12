"""Task Planner — descompone mensajes de usuario en un DAG de subtareas atómicas.

Paquete resultante de la extracción mecánica de
``harness/orchestrator/task_planner.py`` (638 líneas, regla AGR <500):

- ``models.py``: dataclasses ``SubTask`` y ``TaskPlan`` (estructuras + DAG).
- ``templates.py``: ``SUBTASK_TEMPLATES`` (plantillas de descomposición).
- ``planner.py``: clase ``TaskPlanner`` (detección de template + descomposición).

Este ``__init__.py`` re-exporta la MISMA superficie de nombres a nivel de
módulo que el módulo original para mantener backward-compat idéntico:

    from harness.orchestrator.task_planner import TaskPlan, TaskPlanner
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import ClassVar

from harness.memory_rag.compaction import structured_compact

logger = logging.getLogger(__name__)

from .models import SubTask, TaskPlan
from .planner import TaskPlanner
from .templates import SUBTASK_TEMPLATES

__all__ = [
    "SUBTASK_TEMPLATES",
    "ClassVar",
    "SubTask",
    "TaskPlan",
    "TaskPlanner",
    "dataclass",
    "field",
    "logger",
    "logging",
    "structured_compact",
]
