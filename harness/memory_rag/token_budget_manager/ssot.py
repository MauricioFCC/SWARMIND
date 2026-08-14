"""Mixin SSOT (ADR-0040 H6): carga de ``token_budgets.yaml`` y API por rol.

Extraido mecanicamente de ``token_budget_manager.py`` (regla AGR < 500
lineas). Contiene los metodos de carga/validacion del SSOT y la API de
budgets por rol como mixin para que ``TokenBudgetManager`` (en ``core.py``)
conserve la misma API publica y privada sin cambios de logica ni firmas.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..token_budget import DEFAULT_AGENT_BUDGET, DEFAULT_SESSION_BUDGET
from .constants import DEFAULT_COMPRESSION_LEVEL, DEFAULT_COMPRESSION_THRESHOLD
from .yaml_loader import load_yaml

logger = logging.getLogger("harness.memory_rag.token_budget_manager")


class _SSOTMixin:
    """Metodos del SSOT de budgets por rol para ``TokenBudgetManager``."""

    # ------------------------------------------------------------------
    # SSOT: carga de token_budgets.yaml (ADR-0040 H6)
    # ------------------------------------------------------------------

    def _load_budget_config(self, path: Path) -> None:
        """Carga el SSOT de budgets por rol.

        WHAT: Lee ``token_budgets.yaml`` y extrae defaults, role_budgets y
        session_budget; valida que los budgets sean enteros positivos.
        WHY: El YAML es la unica fuente (SSOT) de presupuestos; el runtime
        debe aplicarlos en vez del flat 4000 historico.
        WHERE: ``TokenBudgetManager.__init__`` — una vez por instancia.

        Si el archivo no existe, se conserva el comportamiento historico
        (constantes DEFAULT_AGENT_BUDGET / DEFAULT_SESSION_BUDGET).

        Raises:
            TypeError: Si role_budgets o una entrada de rol no es un mapping.
            ValueError: Si el YAML existe pero tiene budgets invalidos.
        """
        if not path.is_file():
            logger.info(
                "TokenBudgetManager: YAML '%s' no existe; usando constantes historicas "
                "(agent=%d, session=%d)",
                path, DEFAULT_AGENT_BUDGET, DEFAULT_SESSION_BUDGET,
            )
            return

        data = load_yaml(path)
        defaults = data.get("defaults") or {}
        role_budgets = data.get("role_budgets") or {}
        if not isinstance(role_budgets, dict):
            raise TypeError(
                f"WHAT: role_budgets en '{path}' no es un mapping "
                f"(tipo: {type(role_budgets).__name__}). "
                f"WHY: El SSOT requiere role_budgets como dict de roles. "
                f"WHERE: TokenBudgetManager._load_budget_config"
            )

        base_budget = defaults.get("base_budget", DEFAULT_AGENT_BUDGET)
        session_budget = data.get("session_budget", DEFAULT_SESSION_BUDGET)
        threshold = defaults.get("compression_threshold", DEFAULT_COMPRESSION_THRESHOLD)
        self._validate_budget("defaults.base_budget", base_budget)
        self._validate_budget("session_budget", session_budget)
        for role, spec in role_budgets.items():
            if not isinstance(spec, dict):
                raise TypeError(
                    f"WHAT: role_budgets.{role} no es un mapping "
                    f"(tipo: {type(spec).__name__}). "
                    f"WHY: Cada rol declara budget, compression_level e include_principles. "
                    f"WHERE: TokenBudgetManager._load_budget_config"
                )
            self._validate_budget(f"role_budgets.{role}.budget", spec.get("budget"))

        self._base_budget = int(base_budget)
        self._session_budget = int(session_budget)
        self._compression_threshold = float(threshold)
        self._role_budgets = role_budgets
        self._budgets_path = path
        self._yaml_loaded = True
        logger.info(
            "TokenBudgetManager: SSOT '%s' cargado (base=%d, session=%d, threshold=%.2f, roles=%d)",
            path, self._base_budget, self._session_budget, self._compression_threshold,
            len(self._role_budgets),
        )

    @staticmethod
    def _validate_budget(label: str, value: Any) -> None:
        """Valida que un budget sea un entero positivo.

        WHAT: Rechaza budgets no enteros, booleanos o menores a 64 tokens.
        WHY: Budgets invalidos causarian pools con cero tokens o
        comportamiento impredecible en el runtime.
        WHERE: ``TokenBudgetManager._load_budget_config`` — por cada campo.

        Raises:
            TypeError: Si el budget no es un entero.
            ValueError: Si el budget es menor a 64 tokens.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"WHAT: {label}={value!r} debe ser un entero. "
                f"WHY: Los budgets se expresan en tokens enteros. "
                f"WHERE: TokenBudgetManager._validate_budget"
            )
        if value < 64:
            raise ValueError(
                f"WHAT: {label}={value} es demasiado bajo. "
                f"WHY: Un agente necesita al menos 64 tokens. "
                f"WHERE: TokenBudgetManager._validate_budget"
            )

    # ------------------------------------------------------------------
    # API SSOT: budgets por rol (ADR-0040 H6)
    # ------------------------------------------------------------------

    def get_agent_budget(self, agent_name: str) -> int:
        """Retorna el budget de tokens para un agente.

        WHAT: Budget declarado en ``role_budgets[agent].budget`` o, si el rol
        no esta declarado, ``defaults.base_budget`` del SSOT.
        WHY: Cada rol tiene un presupuesto diferencial (ADR-0040 H6) en
        lugar del flat 4000 historico.
        WHERE: Runtime de orquestacion — presupuesto por rol.

        Args:
            agent_name: Nombre del rol/agente (ej. 'guardian').

        Returns:
            Tokens asignados al agente.
        """
        role_budget = self.get_role_budget(agent_name)
        if role_budget is not None:
            return role_budget
        return self._base_budget

    def get_role_budget(self, agent_name: str) -> int | None:
        """Retorna el budget declarado explicitamente para un rol.

        WHAT: ``role_budgets[agent].budget`` o None si el rol no esta
        declarado en el SSOT.
        WHY: El integrador (BudgetManager) necesita distinguir rol conocido
        de rol desconocido para conservar el default historico.
        WHERE: ``harness.memory_rag.token_budget.BudgetManager.register_agent``.

        Args:
            agent_name: Nombre del rol/agente.

        Returns:
            Budget declarado, o None si no hay entrada para el rol.
        """
        role = self._role_budgets.get(agent_name)
        if role is None:
            return None
        return int(role["budget"])

    def get_session_budget(self) -> int:
        """Retorna el presupuesto por sesion del SSOT.

        WHAT: ``session_budget`` del YAML si esta declarado; si no,
        DEFAULT_SESSION_BUDGET (16000).
        WHY: El tope de sesion limita el consumo agregado multi-agente.
        WHERE: Orquestacion — validacion de sesion.

        Returns:
            Presupuesto de tokens por sesion.
        """
        return self._session_budget

    def get_compression_level(self, agent_name: str) -> str:
        """Retorna el nivel de compresion declarado para un agente.

        WHAT: ``role_budgets[agent].compression_level`` (low|medium|high)
        o 'none' si el rol no esta declarado.
        WHY: Roles ligeros (guardian, token-budget-auditor) usan compresion
        agresiva; scientist preserva detalle (low).
        WHERE: Compresion de contexto previa al envio al LLM.

        Args:
            agent_name: Nombre del rol/agente.

        Returns:
            Nivel de compresion ('none', 'low', 'medium', 'high').
        """
        role = self._role_budgets.get(agent_name)
        if role is None:
            return DEFAULT_COMPRESSION_LEVEL
        return str(role.get("compression_level", DEFAULT_COMPRESSION_LEVEL))

    def get_threshold(self) -> float:
        """Retorna el umbral de compresion del SSOT.

        WHAT: ``defaults.compression_threshold`` del YAML (0.85 por defecto).
        WHY: Define cuando se activa la compresion de contexto.
        WHERE: Compresion de contexto — decision de activacion.

        Returns:
            Umbral de compresion (0.0 - 1.0).
        """
        return self._compression_threshold

    def has_budget_config(self) -> bool:
        """Indica si el SSOT fue cargado exitosamente.

        WHAT: True si token_budgets.yaml fue cargado; False si se opera
        con constantes historicas.
        WHY: Los integradores pueden decidir logging o metricas segun la
        fuente de verdad activa.
        WHERE: Diagnostico y telemetria del runtime.

        Returns:
            True si el YAML fue cargado, False en caso contrario.
        """
        return self._yaml_loaded
