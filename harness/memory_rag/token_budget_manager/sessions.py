"""Mixin de seguimiento de sesiones para ``TokenBudgetManager``.

Extraido mecanicamente de ``token_budget_manager.py`` (regla AGR < 500
lineas). Contiene el comportamiento historico de tracking de uso de
tokens por sesion como mixin para que ``TokenBudgetManager`` (en
``core.py``) conserve la misma API publica y privada sin cambios de
logica ni de firmas.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("harness.memory_rag.token_budget_manager")


class _SessionTrackingMixin:
    """Metodos de seguimiento de sesiones para ``TokenBudgetManager``."""

    # ------------------------------------------------------------------
    # Seguimiento de sesiones (comportamiento historico)
    # ------------------------------------------------------------------

    def track_usage(self, session_id: str, tokens: int) -> dict[str, Any]:
        """
        Registra uso de tokens para una sesion.

        WHAT: Incrementa el contador de tokens usados para la sesion.
        Si la sesion no existe, se crea con el presupuesto por defecto.
        WHY: Mantener un registro centralizado de consumo permite
        detectar cuando una sesion se acerca a su limite.
        WHERE: Despues de cada llamada a LLM, registrar tokens consumidos.

        Args:
            session_id: Identificador unico de la sesion.
            tokens: Cantidad de tokens a registrar (debe ser > 0).

        Returns:
            Diccionario con: session_id, total_budget, used, remaining.

        Raises:
            ValueError: Si tokens <= 0.
        """
        if tokens <= 0:
            raise ValueError(
                f"WHAT: tokens={tokens} debe ser > 0. "
                f"WHY: No se pueden registrar 0 o tokens negativos. "
                f"WHERE: TokenBudgetManager.track_usage"
            )

        with self._lock:
            # Crear sesion si no existe
            if session_id not in self._sessions:
                # Gestion de maximo de sesiones: eliminar la mas antigua
                if len(self._sessions) >= self._max_sessions:
                    oldest = min(self._sessions.items(), key=lambda x: x[1][2])
                    del self._sessions[oldest[0]]
                    logger.debug(
                        "TokenBudgetManager: sesion mas antigua '%s' eliminada "
                        "(max_sessions=%d alcanzado)",
                        oldest[0], self._max_sessions,
                    )

                self._sessions[session_id] = (self._default_budget, 0, time.time())
                logger.debug(
                    "TokenBudgetManager: nueva sesion '%s' creada (budget=%d)",
                    session_id, self._default_budget,
                )

            budget, used, created = self._sessions[session_id]
            used += tokens
            self._sessions[session_id] = (budget, used, created)

            remaining = max(0, budget - used)

            logger.debug(
                "TokenBudgetManager: sesion='%s' usado=%d/%d (%.1f%%)",
                session_id, used, budget,
                (used / max(budget, 1)) * 100,
            )

            return {
                "session_id": session_id,
                "total_budget": budget,
                "used": used,
                "remaining": remaining,
                "exhausted": remaining <= 0,
            }

    def get_remaining(self, session_id: str) -> int:
        """
        Obtiene tokens restantes para una sesion.

        Args:
            session_id: Identificador de la sesion.

        Returns:
            Tokens restantes (0 si la sesion no existe o esta agotada).
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return 0
            budget, used, _ = entry
            return max(0, budget - used)

    def get_usage(self, session_id: str) -> dict[str, Any] | None:
        """
        Obtiene el estado completo de uso de una sesion.

        Args:
            session_id: Identificador de la sesion.

        Returns:
            Diccionario con session_id, total_budget, used, remaining,
            usage_pct, exhausted, o None si la sesion no existe.
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            budget, used, _ = entry
            remaining = max(0, budget - used)
            return {
                "session_id": session_id,
                "total_budget": budget,
                "used": used,
                "remaining": remaining,
                "usage_pct": round((used / max(budget, 1)) * 100, 1),
                "exhausted": remaining <= 0,
            }

    def reset_session(self, session_id: str) -> bool:
        """
        Resetea el presupuesto de una sesion (elimina su registro).

        WHAT: Elimina la sesion del registro de uso, liberando su
        presupuesto para futuras sesiones.
        WHY: Cuando una sesion termina, su presupuesto debe liberarse
        para evitar acumulacion de sesiones inactivas.
        WHERE: Al finalizar una sesion de agente o al hacer cleanup.

        Args:
            session_id: Identificador de la sesion a resetear.

        Returns:
            True si la sesion existia y fue eliminada, False si no.
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug("TokenBudgetManager: sesion '%s' resetada", session_id)
                return True
            return False

    def set_budget(self, session_id: str, new_budget: int) -> bool:
        """
        Actualiza el presupuesto total de una sesion existente.

        Args:
            session_id: Identificador de la sesion.
            new_budget: Nuevo presupuesto total (> 0).

        Returns:
            True si se actualizo, False si la sesion no existe.

        Raises:
            ValueError: Si new_budget <= 0.
        """
        if new_budget <= 0:
            raise ValueError(
                f"WHAT: new_budget={new_budget} debe ser > 0. "
                f"WHY: El presupuesto debe ser positivo. "
                f"WHERE: TokenBudgetManager.set_budget"
            )

        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            _, used, created = entry
            self._sessions[session_id] = (new_budget, used, created)
            logger.debug(
                "TokenBudgetManager: sesion '%s' presupuesto actualizado "
                "a %d (used=%d)",
                session_id, new_budget, used,
            )
            return True

    def get_all_sessions(self) -> dict[str, dict[str, Any]]:
        """
        Obtiene el estado de todas las sesiones activas.

        Returns:
            Diccionario {session_id: {total_budget, used, remaining, usage_pct}}.
        """
        with self._lock:
            return {
                sid: {
                    "total_budget": budget,
                    "used": used,
                    "remaining": max(0, budget - used),
                    "usage_pct": round((used / max(budget, 1)) * 100, 1),
                }
                for sid, (budget, used, _) in self._sessions.items()
            }

    def get_stats(self) -> dict[str, Any]:
        """
        Retorna estadisticas del gestor de presupuesto.

        Returns:
            Diccionario con: active_sessions, total_budget_allocated,
            total_used, total_remaining, default_budget.
        """
        with self._lock:
            total_budget = sum(b for b, _, _ in self._sessions.values())
            total_used = sum(u for _, u, _ in self._sessions.values())
            return {
                "active_sessions": len(self._sessions),
                "total_budget_allocated": total_budget,
                "total_used": total_used,
                "total_remaining": max(0, total_budget - total_used),
                "default_budget": self._default_budget,
                "max_sessions": self._max_sessions,
                "usage_pct": round(
                    (total_used / max(total_budget, 1)) * 100, 1
                ),
            }
