"""run_commands â command handlers del Harness CLI (paquete <500L).

Punto de entrada con RESOLUCION DINAMICA: todas las llamadas publicas
pasan por ``run_command``, que resuelve cada handler en tiempo de
ejecucion via ``sys.modules`` (patron late-binding). Esto garantiza que
cualquier funcion del paquete sea parcheable con
``unittest.mock.patch("harness.run_commands.<funcion>")`` sin importar
en que submodulo este definida.

Estructura:
- handlers_iteration.py : comandos !iteration *
- handlers_other.py     : comandos !db / !hooks / !rag
- handlers_extra.py     : !evolve / !schedule / !hermes / watch mode
- colors.py             : helpers de impresion con color

Uso::

    from harness.run_commands import run_command
    run_command("!iteration end --quick", harness_root)
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

from .colors import (
    _BOLD,
    _CYAN,
    _GREEN,
    _RED,
    _RESET,
    _YELLOW,
    _bold,
    _cyan,
    _err,
    _ok,
    _safe_print,
    _warn,
)
from .handlers_extra import (
    _apply_model_routing,
    _check_hitl,
    _get_files_to_watch,
    _handle_evolve_mutate,
    _handle_hermes,
    _handle_hooks_status,
    _handle_schedule_add,
    _handle_schedule_list,
    _handle_watch_mode,
    _run_guardrails,
)
from .handlers_iteration import (
    _handle_iteration_auto,
    _handle_iteration_diff,
    _handle_iteration_end,
    _handle_iteration_history,
    _handle_iteration_quick,
    _handle_iteration_report,
    _parse_iteration_flags,
)
from .handlers_other import (
    _handle_db_list_imports,
    _handle_db_migrate,
    _handle_db_rollback,
    _handle_db_stats,
    _handle_hooks_install,
    _handle_hooks_uninstall,
    _handle_rag_ingest,
    _handle_rag_stats,
)

logger = logging.getLogger("harness.run_commands")

# ---------------------------------------------------------------------------
# Tabla canonica de comandos (fuente unica del despacho)
# ---------------------------------------------------------------------------
# (prefijo_minusculas, nombre_del_handler, firma_de_llamada)
# firmas: "store_cmd" -> h(store, cmd) | "store" -> h(store)
#         "cmd"       -> h(cmd)       | "none"  -> h()
#         "root"      -> h(cmd, harness_root)
_COMMAND_TABLE: tuple[tuple[str, str, str], ...] = (
    ("!evolve mutate", "_handle_evolve_mutate", "store_cmd"),
    ("!schedule add", "_handle_schedule_add", "store_cmd"),
    ("!schedule list", "_handle_schedule_list", "store"),
    ("!db migrate", "_handle_db_migrate", "store_cmd"),
    ("!db list-imports", "_handle_db_list_imports", "none"),
    ("!db stats", "_handle_db_stats", "store"),
    ("!db rollback", "_handle_db_rollback", "cmd"),
    ("!iteration end", "_handle_iteration_end", "root"),
    ("!iteration quick", "_handle_iteration_quick", "root"),
    ("!iteration auto", "_handle_iteration_auto", "root"),
    ("!iteration history", "_handle_iteration_history", "cmd"),
    ("!iteration diff", "_handle_iteration_diff", "cmd"),
    ("!iteration report", "_handle_iteration_report", "none"),
    ("!hooks install", "_handle_hooks_install", "none"),
    ("!hooks uninstall", "_handle_hooks_uninstall", "none"),
    ("!hooks status", "_handle_hooks_status", "none"),
    ("!rag ingest", "_handle_rag_ingest", "store_cmd"),
    ("!rag stats", "_handle_rag_stats", "store"),
    ("!hermes", "_handle_hermes", "cmd"),
)


def _get_pkg_attr(attr_name: str, fallback_fn: Any) -> Any:
    """Obtiene un atributo del paquete en tiempo de ejecucion (late-binding).

    Si una prueba aplico ``mock.patch("harness.run_commands.<attr>")``,
    retorna el Mock; si no, el fallback (referencia directa al import).

    Args:
        attr_name: Nombre del atributo en el namespace del paquete.
        fallback_fn: Funcion original a usar si el paquete no esta en
            ``sys.modules`` o no tiene el atributo.

    Returns:
        El atributo resuelto dinamicamente (Mock u original).
    """
    pkg = sys.modules.get(__name__)
    return getattr(pkg, attr_name, fallback_fn) if pkg else fallback_fn


def _create_store() -> Any:
    """Crea perezosamente el vector store para handlers que lo requieren.

    Returns:
        Instancia de LanceVectorStore.

    Raises:
        RuntimeError: si el backend no esta disponible
            (WHAT fallo import / WHY store requerido / WHERE modulo).
    """
    try:
        from harness.db.vector_store import LanceVectorStore
    except ImportError as exc:
        raise RuntimeError(
            f"RuntimeError: no se pudo crear el vector store ({exc}). WHY: "
            "el comando requiere LanceVectorStore y su backend no esta "
            "disponible. WHERE: run_commands._create_store."
        ) from exc
    return LanceVectorStore()


def run_command(
    cmd: str, harness_root: Path | None = None, **kwargs: Any
) -> Any:
    """Despachador principal de comandos ``!`` del CLI.

    Resuelve cada handler dinamicamente via :func:`_get_pkg_attr` para
    respetar los mocks aplicados en los tests sobre el namespace del
    paquete. El store se crea perezosamente solo para comandos que lo
    requieren (o usa el kwarg ``store`` si se provee).

    Args:
        cmd: Comando completo (p. ej. ``"!iteration end --quick"``).
        harness_root: Raiz del harness (requerido por comandos de iteracion).
        **kwargs: Reservado; solo se consume ``store`` para inyectar el
            vector store y evitar su creacion perezosa.

    Returns:
        Lo que retorne el handler (normalmente None).

    Raises:
        ValueError: si el comando no esta en la tabla canonica
            (WHAT desconocido / WHY sin handler asociado / WHERE tabla).
    """
    cmd_clean = cmd.strip().lower()
    for prefix, handler_name, signature in _COMMAND_TABLE:
        if not cmd_clean.startswith(prefix):
            continue
        handler = _get_pkg_attr(handler_name, globals()[handler_name])
        if signature in ("store_cmd", "store"):
            store = kwargs.pop("store", None) or _create_store()
        if signature == "store_cmd":
            return handler(store, cmd)
        if signature == "store":
            return handler(store)
        if signature == "cmd":
            return handler(cmd)
        if signature == "root":
            return handler(cmd, harness_root)
        return handler()
    raise ValueError(
        f"ValueError: comando no reconocido '{cmd}'. WHY: no existe en la "
        "tabla canonica de run_commands. WHERE: run_command._COMMAND_TABLE."
    )


__all__ = [
    "_BOLD",
    "_CYAN",
    "_GREEN",
    "_RED",
    "_RESET",
    "_YELLOW",
    "_apply_model_routing",
    "_bold",
    "_check_hitl",
    "_create_store",
    "_cyan",
    "_err",
    "_get_files_to_watch",
    "_get_pkg_attr",
    "_handle_db_list_imports",
    "_handle_db_migrate",
    "_handle_db_rollback",
    "_handle_db_stats",
    "_handle_evolve_mutate",
    "_handle_hermes",
    "_handle_hooks_install",
    "_handle_hooks_status",
    "_handle_hooks_uninstall",
    "_handle_iteration_auto",
    "_handle_iteration_diff",
    "_handle_iteration_end",
    "_handle_iteration_history",
    "_handle_iteration_quick",
    "_handle_iteration_report",
    "_handle_rag_ingest",
    "_handle_rag_stats",
    "_handle_schedule_add",
    "_handle_schedule_list",
    "_handle_watch_mode",
    "_ok",
    "_parse_iteration_flags",
    "_run_guardrails",
    "_safe_print",
    "_warn",
    "logger",
    "run_command",
    "sys",
    "time",
]
