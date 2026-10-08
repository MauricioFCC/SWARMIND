"""local_first.py — Politica local-first + cloud como oraculo/fallback.

WHAT: decide cuando una tarea debe ejecutarse en el backend local
(llama.cpp/llama-swap) y cuando se paga cloud como oraculo de minima
intervencion. La fuente es el entorno (12-Factor), con defaults seguros.
WHY: frontier 2026 — local-first reduce tokens cloud; el cloud se reserva
como oraculo (solo si local no basta) o como fallback cuando no hay GPU.
WHERE: ``run_commands._apply_model_routing`` (decision local/cloud) y
``run._try_local_execution`` (ejecucion + oraculo).

Uso:
    policy = LocalFirstPolicy.from_env()
    if policy.should_use_local(backend_available=up, force_cloud=False):
        use_local()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("harness.model_router.local_first")

#: Overrides por entorno (12-Factor; no hardcode de politica operativa).
ENV_ENABLED = "SWARMIND_LOCAL_FIRST_ENABLED"
ENV_MAX_PARALLEL = "SWARMIND_LOCAL_FIRST_MAX_PARALLEL"
ENV_ALLOW_OPEN_TASKS = "SWARMIND_LOCAL_FIRST_ALLOW_OPEN_TASKS"
ENV_CLOUD_ORACLE = "SWARMIND_LOCAL_FIRST_CLOUD_ORACLE"

#: Defaults seguros: local-first activo, 2 en paralelo (alineado con
#: `--parallel 2` de llama-server; mas workers solo encolan en el server),
#: tareas abiertas permitidas (el executor gatea por tier) y cloud oraculo.
DEFAULT_ENABLED = True
DEFAULT_MAX_PARALLEL = 2
DEFAULT_ALLOW_OPEN_TASKS = True
DEFAULT_CLOUD_ORACLE = True

#: Literales aceptados para booleanos de entorno.
_TRUE_LITERALS = frozenset({"1", "true", "yes", "on", "si"})
_FALSE_LITERALS = frozenset({"0", "false", "no", "off"})


def _env_bool(name: str, default: bool) -> bool:
    """Lee un booleano de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si no existe o no parsea.

    Returns:
        Booleano leido o ``default``; nunca lanza.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_LITERALS:
        return True
    if value in _FALSE_LITERALS:
        return False
    logger.warning("local_first: %s=%r no es booleano; uso %s", name, raw, default)
    return default


def _env_int(name: str, default: int) -> int:
    """Lee un entero de entorno (default si ausente o invalido).

    Args:
        name: Nombre de la variable de entorno.
        default: Valor si no existe o no parsea.

    Returns:
        Entero leido o ``default``; nunca lanza.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("local_first: %s=%r no es entero; uso %s", name, raw, default)
        return default


@dataclass(frozen=True)
class LocalFirstPolicy:
    """Politica local-first (inmutable) con cloud como oraculo/fallback.

    Attributes:
        enabled: True = preferir local cuando el backend responde.
        max_parallel: Maximo de tareas locales concurrentes (>=1).
        allow_open_tasks: True = intentar local tambien en tareas abiertas.
        cloud_oracle: True = cloud solo si local no basta (oraculo).

    Raises:
        ValueError: Si ``max_parallel`` es menor que 1.
    """

    enabled: bool = DEFAULT_ENABLED
    max_parallel: int = DEFAULT_MAX_PARALLEL
    allow_open_tasks: bool = DEFAULT_ALLOW_OPEN_TASKS
    cloud_oracle: bool = DEFAULT_CLOUD_ORACLE

    def __post_init__(self) -> None:
        """Valida ``max_parallel`` (WHAT+WHY+WHERE si viola)."""
        if self.max_parallel < 1:
            raise ValueError(
                f"WHAT: max_parallel invalido ({self.max_parallel}). "
                "WHY: debe haber al menos una ejecucion local concurrente. "
                "WHERE: LocalFirstPolicy.__post_init__"
            )

    @classmethod
    def from_env(cls) -> LocalFirstPolicy:
        """Construye la politica desde el entorno (defaults seguros).

        Returns:
            LocalFirstPolicy con los overrides presentes.

        Raises:
            ValueError: Si ``max_parallel`` del entorno es menor que 1.
        """
        return cls(
            enabled=_env_bool(ENV_ENABLED, DEFAULT_ENABLED),
            max_parallel=_env_int(ENV_MAX_PARALLEL, DEFAULT_MAX_PARALLEL),
            allow_open_tasks=_env_bool(ENV_ALLOW_OPEN_TASKS, DEFAULT_ALLOW_OPEN_TASKS),
            cloud_oracle=_env_bool(ENV_CLOUD_ORACLE, DEFAULT_CLOUD_ORACLE),
        )

    def should_use_local(self, *, backend_available: bool, force_cloud: bool) -> bool:
        """Decide si corresponde ejecutar en local.

        Args:
            backend_available: True si el backend local responde (is_up).
            force_cloud: True si el usuario forzo cloud (--force-cloud).

        Returns:
            True solo si la politica esta activa, no se forzo cloud y el
            backend local esta disponible; False en cualquier otro caso.
        """
        if force_cloud:
            return False
        if not self.enabled:
            return False
        return backend_available
