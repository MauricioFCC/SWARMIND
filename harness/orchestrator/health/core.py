"""Health core — clase principal ``AgentHealthChecker``.

Extraccion mecanica del modulo original
``harness/orchestrator/health.py`` (sin cambios de logica ni firmas).
La clase compone los mixins por responsabilidad:

- ``_ChecksMixin`` (checks_mixin.py): check_liveness/check_readiness.
- ``_CognitiveMixin`` (cognitive_mixin.py): check_cognitive + gestion de sesiones.
"""
from __future__ import annotations

import logging
from typing import Any

from .checks_mixin import _ChecksMixin
from .cognitive import CognitiveState
from .cognitive_mixin import _CognitiveMixin

logger = logging.getLogger("harness.orchestrator.health")


class AgentHealthChecker(_ChecksMixin, _CognitiveMixin):
    """
    Health Checker multi-nivel para sistemas de agentes.

    Uso:
        checker = AgentHealthChecker(vector_store=store)
        status = checker.check_all()
        if not status["cognitive"].healthy:
            # tomar accion correctiva

    Opcionalmente acepta un TelemetryTracker para vincular CognitiveState
    con SessionTelemetry, eliminando la duplicacion de datos.
    """

    def __init__(
        self,
        vector_store: Any | None = None,
        telemetry_tracker: Any | None = None,
    ) -> None:
        self._store = vector_store
        self._telemetry_tracker = telemetry_tracker
        self._cognitive_states: dict[str, CognitiveState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_hardware_info(self) -> dict:
        """Info de hardware de aceleracion (GPU/CPU) para observabilidad.

        Usa harness.gpu_accel.get_device_info() (lazy import para no
        romper entornos sin torch). Reporta: available, device,
        device_name, memory_gb, torch_version y cuda_version.

        Returns:
            Dict con la informacion del dispositivo.
        """
        try:
            from harness.gpu_accel import get_device_info
            return get_device_info()
        except ImportError:
            return {
                "available": False,
                "device": "cpu",
                "device_name": "CPU (torch no instalado)",
                "memory_gb": 0.0,
            }
