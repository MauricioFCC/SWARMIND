"""Clase principal ``TokenBudgetManager``.

Extraido mecanicamente de ``token_budget_manager.py`` (regla AGR < 500
lineas). La clase conserva la misma API publica y privada; los metodos
del SSOT viven en el mixin de ``ssot.py`` y el tracking de sesiones en
``sessions.py``. Sin cambios de logica.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from ..token_budget import DEFAULT_AGENT_BUDGET, DEFAULT_SESSION_BUDGET
from .constants import DEFAULT_COMPRESSION_THRESHOLD, DEFAULT_TOKEN_BUDGETS_PATH
from .sessions import _SessionTrackingMixin
from .ssot import _SSOTMixin

logger = logging.getLogger("harness.memory_rag.token_budget_manager")


class TokenBudgetManager(_SSOTMixin, _SessionTrackingMixin):
    """
    Gestiona el presupuesto de tokens por sesion de agente.

    WHAT: Realiza seguimiento del uso de tokens por sesion, permitiendo
    consultar tokens restantes y resetear presupuestos.
    WHY: Las sesiones multi-agente necesitan control centralizado de
    tokens para evitar que un agente consuma todo el presupuesto.
    WHERE: Usado por el gateway y el orquestador de agentes para
    gestionar el consumo de tokens por sesion.

    Desde ADR-0040 H6, ademas carga el SSOT ``.opencode/config/token_budgets.yaml``
    y expone budgets por rol (role_budgets), nivel de compresion
    (compression_level) y umbral de compresion (compression_threshold).
    Si el YAML no existe, opera con las constantes historicas
    (DEFAULT_AGENT_BUDGET / DEFAULT_SESSION_BUDGET).

    Diferencia con ``BudgetManager`` (token_budget.py):
    - ``BudgetManager`` maneja pools con prioridades y redistribucion.
    - ``TokenBudgetManager`` es un tracker ligero de uso por sesion + SSOT.

    Uso:
        manager = TokenBudgetManager(default_budget=4000)
        manager.track_usage("session-1", 150)
        remaining = manager.get_remaining("session-1")
        manager.reset_session("session-1")
        budget = manager.get_agent_budget("guardian")   # 2048 (SSOT)
        level = manager.get_compression_level("guardian")  # 'high'
    """

    def __init__(
        self,
        default_budget: int = 4000,
        max_sessions: int = 100,
        yaml_path: str | Path | None = None,
    ) -> None:
        """
        Inicializa el TokenBudgetManager.

        Args:
            default_budget: Presupuesto por defecto para nuevas sesiones.
                Default: 4000 tokens.
            max_sessions: Maximo de sesiones activas simultaneas.
                Cuando se excede, se elimina la sesion mas antigua.
                Default: 100.
            yaml_path: Ruta del SSOT de budgets (token_budgets.yaml).
                Default: ``.opencode/config/token_budgets.yaml`` relativo al
                repo root. Si el archivo no existe, el manager opera con las
                constantes historicas.

        Raises:
            ValueError: Si default_budget < 64, max_sessions < 1, o el YAML
                existe pero esta mal formado o contiene budgets invalidos.
            TypeError: Si el YAML tiene secciones con tipos incorrectos.
        """
        if default_budget < 64:
            raise ValueError(
                f"WHAT: default_budget={default_budget} es demasiado bajo. "
                f"WHY: Una sesion necesita al menos 64 tokens. "
                f"WHERE: TokenBudgetManager.__init__"
            )
        if max_sessions < 1:
            raise ValueError(
                f"WHAT: max_sessions={max_sessions} debe ser >= 1. "
                f"WHY: Debe haber al menos 1 sesion activa. "
                f"WHERE: TokenBudgetManager.__init__"
            )

        self._default_budget = default_budget
        self._max_sessions = max_sessions

        # {session_id: (budget_total, tokens_used, timestamp)}
        self._sessions: dict[str, tuple[int, int, float]] = {}
        self._lock = threading.Lock()

        # Estado cargado del SSOT (ADR-0040 H6)
        self._budgets_path: Path | None = None
        self._role_budgets: dict[str, dict[str, Any]] = {}
        self._base_budget: int = DEFAULT_AGENT_BUDGET
        self._session_budget: int = DEFAULT_SESSION_BUDGET
        self._compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD
        self._yaml_loaded = False

        self._load_budget_config(Path(yaml_path) if yaml_path is not None else DEFAULT_TOKEN_BUDGETS_PATH)

        logger.info(
            "TokenBudgetManager initialized (budget=%d, max_sessions=%d, yaml=%s)",
            default_budget, max_sessions, self._budgets_path or "none",
        )
