"""auto_fix_all — Correccion masiva de bugs detectados por pre-commit hook.

Antes: harness/scripts/auto_fix_all.py (547 lineas).
Ahora: paquete ``harness/scripts/auto_fix_all/``:

- ``constants.py``: PROJECT_ROOT, SCOPES y SKIP_FILES.
- ``prints.py``: reemplazo print() -> logging.
- ``typehints.py``: agregado de type hints faltantes.
- ``docstrings.py``: agregado de docstrings faltantes.
- ``todos.py``: fixes triviales de TODO/FIXME.
- ``runner.py``: ``fix_file`` y ``main``.
- ``__main__.py``: entrada CLI (preserva ``python -m harness.scripts.auto_fix_all``).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat. Uso:

    python -m harness.scripts.auto_fix_all [--dry-run]

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from .constants import PROJECT_ROOT, SCOPES, SKIP_FILES
from .docstrings import (
    SIMPLE_DOCSTRINGS,
)
from .docstrings import (
    _fix_missing_docstrings as _fix_missing_docstrings,
)
from .docstrings import (
    _should_skip_docstring as _should_skip_docstring,
)
from .prints import (
    _ensure_logger_setup as _ensure_logger_setup,
)
from .prints import (
    _replace_print_with_logging as _replace_print_with_logging,
)
from .runner import fix_file, main
from .todos import TODO_FIXES
from .todos import _fix_todos as _fix_todos
from .typehints import (
    _ensure_typing_import as _ensure_typing_import,
)
from .typehints import (
    _fix_missing_type_hints as _fix_missing_type_hints,
)
from .typehints import (
    _should_skip_type_hint as _should_skip_type_hint,
)

__all__ = [
    "PROJECT_ROOT",
    "SCOPES",
    "SIMPLE_DOCSTRINGS",
    "SKIP_FILES",
    "TODO_FIXES",
    "fix_file",
    "main",
]
