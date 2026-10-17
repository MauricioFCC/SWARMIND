"""reverse_engineering — enrutamiento de targets RE (REA) al engine correcto.

Expone :class:`~harness.reverse_engineering.target_router.ReRoute` y la funcion
:func:`~harness.reverse_engineering.target_router.route`, que elige el metodo
REA, el provider (engine) y la evidencia esperada por tipo de artefacto,
aplicando el guardrail etico del skill ``reverse-engineering``.
"""

from __future__ import annotations

from harness.reverse_engineering.target_router import (
    ENV_ANALYSIS_PROVIDER,
    PROVIDERS,
    TARGET_DOTNET,
    TARGET_GO,
    TARGET_JAVASCRIPT,
    TARGET_NATIVE,
    TARGET_NETWORK_CAPTURE,
    TARGET_SQLITE,
    TARGET_UNKNOWN,
    TARGET_WEBSITE,
    ReRoute,
    detect_target_type,
    route,
)

__all__ = [
    "ENV_ANALYSIS_PROVIDER",
    "PROVIDERS",
    "TARGET_DOTNET",
    "TARGET_GO",
    "TARGET_JAVASCRIPT",
    "TARGET_NATIVE",
    "TARGET_NETWORK_CAPTURE",
    "TARGET_SQLITE",
    "TARGET_UNKNOWN",
    "TARGET_WEBSITE",
    "ReRoute",
    "detect_target_type",
    "route",
]
