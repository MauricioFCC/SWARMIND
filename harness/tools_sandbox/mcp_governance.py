"""mcp_governance — Capa de gobernanza para ejecución de herramientas MCP.

Implementa el principio del ADR-0049: "la gobernanza se convierte en la
capa de control". Antes de ejecutar cualquier tool MCP se valida:

1. **Autorización**: el agente tiene una política registrada y la tool está
   en su allowlist (mínimo privilegio).
2. **Cuota**: límite de llamadas por minuto por agente (protección de costo
   y anti-abuso).
3. **Auditoría**: cada intento (permitido o denegado) queda registrado en un
   audit trail inmutable con parámetros enmascarados (regla SEG).

WHAT: envuelve ``MCPManager.execute`` con autorización + cuota + auditoría.
WHY: sin capa de control explícita, cualquier agente puede invocar cualquier
tool externa; el audit trail es la "prueba de defensa" (ADR-0051, pregunta 2).
WHERE: ``harness/tools_sandbox/``, junto a ``mcp_manager.py`` que envuelve.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from harness.tools_sandbox.mcp_manager import MCPManager

logger = logging.getLogger(__name__)

__all__ = [
    "AuditEntry",
    "GovernanceDecision",
    "MCPGovernor",
    "ToolPolicy",
]

# Ventana de la cuota deslizante, en segundos.
_RATE_WINDOW_SECONDS = 60.0

# Longitud máxima del audit trail en memoria (los más antiguos se descartan).
_AUDIT_MAX_ENTRIES = 10_000


@dataclass(frozen=True)
class ToolPolicy:
    """Política de mínimo privilegio para un agente.

    Attributes:
        agent_id: Identificador único del agente.
        allowed_tools: Tools que el agente puede invocar.
        max_calls_per_minute: Cuota de invocaciones por ventana deslizante.
    """

    agent_id: str
    allowed_tools: frozenset[str]
    max_calls_per_minute: int = 30


@dataclass(frozen=True)
class GovernanceDecision:
    """Resultado de una decisión de autorización.

    Attributes:
        allowed: Si la llamada está autorizada.
        reason: Motivo legible de la decisión (para logs y auditoría).
    """

    allowed: bool
    reason: str


@dataclass(frozen=True)
class AuditEntry:
    """Registro inmutable de un intento de ejecución de tool.

    Los parámetros NUNCA se almacenan en crudo (regla SEG: mask logs);
    solo se guardan los nombres de las claves.

    Attributes:
        timestamp: Epoch seconds del intento.
        agent_id: Agente que intentó la llamada.
        tool_name: Tool solicitada.
        param_keys: Nombres de las claves de parámetros (sin valores).
        allowed: Si la llamada fue autorizada.
        reason: Motivo de la decisión.
    """

    timestamp: float
    agent_id: str
    tool_name: str
    param_keys: tuple[str, ...]
    allowed: bool
    reason: str


@dataclass
class _AgentRuntimeState:
    """Estado mutable por agente: timestamps de llamadas recientes."""

    call_times: deque[float] = field(default_factory=deque)


class MCPGovernor:
    """Capa de control entre agentes y ``MCPManager``.

    Uso típico::

        governor = MCPGovernor(manager)
        governor.register_policy(ToolPolicy(
            agent_id="builder",
            allowed_tools=frozenset({"read_file"}),
        ))
        result = governor.execute("builder", "read_file", {"path": "/tmp"})
    """

    def __init__(self, manager: MCPManager) -> None:
        """Inicializa el gobernador sobre un manager existente.

        Args:
            manager: Pool MCP que resuelve y ejecuta las tools.
        """
        self._manager = manager
        self._policies: dict[str, ToolPolicy] = {}
        self._runtime: dict[str, _AgentRuntimeState] = {}
        self._audit: deque[AuditEntry] = deque(maxlen=_AUDIT_MAX_ENTRIES)

    # ------------------------------------------------------------------
    # Registro de políticas
    # ------------------------------------------------------------------

    def register_policy(self, policy: ToolPolicy) -> None:
        """Registra (o reemplaza) la política de un agente.

        Args:
            policy: Política de mínimo privilegio del agente.
        """
        if not policy.agent_id:
            raise ValueError(
                "WHAT: agent_id vacío en ToolPolicy. "
                "WHY: toda política debe estar asociada a un agente identificable. "
                "WHERE: MCPGovernor.register_policy()"
            )
        self._policies[policy.agent_id] = policy
        self._runtime.setdefault(policy.agent_id, _AgentRuntimeState())
        logger.info("Política MCP registrada para '%s' (%d tools)", policy.agent_id, len(policy.allowed_tools))

    def unregister_policy(self, agent_id: str) -> None:
        """Elimina la política de un agente; pierde acceso a todas las tools.

        Args:
            agent_id: Identificador del agente.
        """
        self._policies.pop(agent_id, None)

    def get_audit_trail(self) -> tuple[AuditEntry, ...]:
        """Devuelve una vista inmutable del audit trail.

        Returns:
            Tupla de entradas en orden cronológico.
        """
        return tuple(self._audit)

    # ------------------------------------------------------------------
    # Autorización y ejecución
    # ------------------------------------------------------------------

    def authorize(self, agent_id: str, tool_name: str) -> GovernanceDecision:
        """Valida si un agente puede invocar una tool.

        Args:
            agent_id: Identificador del agente.
            tool_name: Nombre de la tool solicitada.

        Returns:
            Decisión con veredicto y motivo.
        """
        policy = self._policies.get(agent_id)
        if policy is None:
            return GovernanceDecision(
                allowed=False,
                reason=f"Agente '{agent_id}' sin política registrada (deny-by-default)",
            )
        if tool_name not in policy.allowed_tools:
            return GovernanceDecision(
                allowed=False,
                reason=(
                    f"Tool '{tool_name}' fuera del allowlist del agente "
                    f"'{agent_id}' (mínimo privilegio)"
                ),
            )
        if not self._consume_quota(agent_id):
            return GovernanceDecision(
                allowed=False,
                reason=(
                    f"Cuota excedida para '{agent_id}' "
                    f"(>{policy.max_calls_per_minute}/min)"
                ),
            )
        return GovernanceDecision(allowed=True, reason="Autorizado por política")

    def execute(
        self,
        agent_id: str,
        tool_name: str,
        params: dict[str, Any],
        timeout: int | None = None,
    ) -> Any:
        """Autoriza, audita y ejecuta una tool vía el manager.

        Args:
            agent_id: Identificador del agente.
            tool_name: Nombre de la tool.
            params: Parámetros de la tool (solo sus claves se auditan).
            timeout: Timeout opcional en segundos para la ejecución.

        Returns:
            El ``MCPResult`` producido por el manager si fue autorizado.

        Raises:
            PermissionError: Si la autorización deniega la llamada.
        """
        decision = self.authorize(agent_id, tool_name)
        self._record(agent_id, tool_name, params, decision)
        if not decision.allowed:
            raise PermissionError(
                f"WHAT: ejecución de tool '{tool_name}' denegada para '{agent_id}'. "
                f"WHY: {decision.reason}. "
                "WHERE: MCPGovernor.execute()"
            )
        return self._manager.execute(tool_name, params, timeout=timeout)

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _consume_quota(self, agent_id: str) -> bool:
        """Consume un slot de la cuota deslizante si hay disponibilidad.

        Args:
            agent_id: Identificador del agente.

        Returns:
            True si el slot fue consumido, False si la cuota está agotada.
        """
        policy = self._policies[agent_id]
        state = self._runtime[agent_id]
        now = time.monotonic()
        while state.call_times and (now - state.call_times[0]) > _RATE_WINDOW_SECONDS:
            state.call_times.popleft()
        if len(state.call_times) >= policy.max_calls_per_minute:
            return False
        state.call_times.append(now)
        return True

    def _record(
        self,
        agent_id: str,
        tool_name: str,
        params: dict[str, Any],
        decision: GovernanceDecision,
    ) -> None:
        """Registra el intento en el audit trail con parámetros enmascarados.

        Args:
            agent_id: Identificador del agente.
            tool_name: Nombre de la tool.
            params: Parámetros originales (solo se auditan las claves).
            decision: Decisión de autorización asociada.
        """
        entry = AuditEntry(
            timestamp=time.time(),
            agent_id=agent_id,
            tool_name=tool_name,
            param_keys=tuple(sorted(params.keys())),
            allowed=decision.allowed,
            reason=decision.reason,
        )
        self._audit.append(entry)
        if not decision.allowed:
            logger.warning("MCP denegado: agente='%s' tool='%s' (%s)", agent_id, tool_name, decision.reason)
