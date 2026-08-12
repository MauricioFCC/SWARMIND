"""TokenBudgetManager — Gestion de presupuesto de tokens por sesion.

Este paquete reemplaza al modulo ``token_budget_manager.py`` (regla AGR:
archivo < 500 lineas). Todos los simbolos publicos del modulo original se
re-exportan desde aqui, por lo que los imports existentes
(``from harness.memory_rag.token_budget_manager import TokenBudgetManager``)
siguen funcionando identicos y los parches de tests que apuntan a
``harness.memory_rag.token_budget_manager.X`` siguen afectando al paquete.
"""
from __future__ import annotations

import logging

from .constants import (
    DEFAULT_COMPRESSION_LEVEL,
    DEFAULT_COMPRESSION_THRESHOLD,
    DEFAULT_TOKEN_BUDGETS_PATH,
)
from .core import TokenBudgetManager
from .yaml_loader import load_yaml

logger = logging.getLogger("harness.memory_rag.token_budget_manager")

__all__ = [
    "DEFAULT_COMPRESSION_LEVEL",
    "DEFAULT_COMPRESSION_THRESHOLD",
    "DEFAULT_TOKEN_BUDGETS_PATH",
    "TokenBudgetManager",
    "load_yaml",
    "logger",
]
