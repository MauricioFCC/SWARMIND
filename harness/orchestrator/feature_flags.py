"""feature_flags.py — Flags para trabajo incompleto (ADR-0083, trunk-based).

WHAT: Registro de feature flags con default seguro (off) y override por
entorno (`SWARMIND_FF_<NAME>=1`); snapshot inmutable.
WHY: Frontera (trunk-based/DORA elite): sin flags no hay trunk real —
merge != release (dark ship). El trabajo incompleto de agentes va tras
flag, nunca en rama larga.
WHERE: `task_planner`/`parallel_executor` antes de activar codigo nuevo;
CI puede encender flags por entorno.

Uso:
    flags = FeatureFlags({"nuevo-router": True})
    if flags.is_enabled("nuevo-router"): usar_nuevo()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.feature_flags")

#: Prefijo de override por entorno.
ENV_PREFIX = "SWARMIND_FF_"


@dataclass(frozen=True)
class FeatureFlags:
    """Snapshot inmutable de feature flags.

    Attributes:
        flags: Mapa nombre -> habilitado (default: todo off).
    """

    flags: dict[str, bool] | None = None

    def __post_init__(self) -> None:
        """Normaliza el mapa a dict vacio si es None."""
        if self.flags is None:
            object.__setattr__(self, "flags", {})

    @classmethod
    def from_env(cls) -> FeatureFlags:
        """Construye flags desde el entorno (`SWARMIND_FF_<NAME>=1`).

        Returns:
            FeatureFlags con los overrides activos (nombre en minusculas,
            guiones bajos convertidos a guiones).
        """
        found: dict[str, bool] = {}
        for key, value in os.environ.items():
            if key.startswith(ENV_PREFIX) and value.strip() == "1":
                name = key[len(ENV_PREFIX):].lower().replace("_", "-")
                found[name] = True
        if found:
            logger.info("feature_flags: overrides por entorno: %s", sorted(found))
        return cls(flags=found)

    def is_enabled(self, name: str) -> bool:
        """Evalua un flag (default seguro: off).

        Args:
            name: Nombre del flag (no vacio).

        Returns:
            True solo si esta explicitamente encendido.

        Raises:
            ValueError: Si el nombre esta vacio (WHAT+WHY+WHERE).
        """
        if not name.strip():
            raise ValueError(
                "WHAT: nombre de flag vacio. "
                "WHY: sin nombre no hay flag que evaluar. "
                "WHERE: FeatureFlags.is_enabled"
            )
        return bool((self.flags or {}).get(name.strip()))


def is_enabled(name: str) -> bool:
    """Atajo: evalua contra flags por defecto (todo off) + entorno.

    Args:
        name: Nombre del flag.

    Returns:
        True si `SWARMIND_FF_<NAME>=1` esta activo.
    """
    return FeatureFlags.from_env().is_enabled(name)
