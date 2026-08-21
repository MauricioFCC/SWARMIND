"""governance — Las cuatro preguntas de gobernanza de agentes IA.

Implementa el ADR-0051: una gobernanza que sobrevive la revisión por
comité pero falla en el momento de la decisión real es inútil. Las cuatro
preguntas convierten políticas abstractas en capacidades operativas:

1. **Autoridad**   — ¿Puedes pausarla?      -> kill-switch registrado.
2. **Defensa**     — ¿Puedes demostrarlo?   -> decisiones registradas con
                                                acción, elección y rationale.
3. **Visibilidad** — ¿Puedes verla?         -> monitor recibiendo eventos.
4. **Respuesta**   — ¿Puedes hablar de ella?-> procedimiento de incidentes
                                                con responsable y portavoz.

Alineado con NIST AI RMF (función MANAGE), EU AI Act Art. 72 y el registro
de decisiones BTR (action+chosen+rationale+confidence).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "AgentGovernanceBoard",
    "FourQuestionsReport",
    "GovernanceDecisionRecord",
    "IncidentProcedure",
]

# Callbacks de monitoreo: reciben el nombre del evento y su payload.
MonitorCallback = Callable[[str, dict[str, Any]], None]

# Kill switch: detiene un agente/sistema por nombre; True si se detuvo.
KillSwitch = Callable[[str], bool]


@dataclass(frozen=True)
class IncidentProcedure:
    """Procedimiento de respuesta a incidentes (pregunta 4).

    Attributes:
        owner: Responsable único autorizado para coordinar la respuesta.
        runbook_ref: Referencia al runbook documentado.
        spokesperson: Quién habla en nombre de la institución.
    """

    owner: str
    runbook_ref: str
    spokesperson: str


@dataclass(frozen=True)
class GovernanceDecisionRecord:
    """Registro de una decisión de gobernanza (pregunta 2 / patrón BTR).

    Attributes:
        timestamp: Epoch seconds de la decisión.
        action: Acción ejecutada (ej. ``pause``, ``register_policy``).
        chosen: Elección concreta tomada.
        rationale: Por qué se eligió (obligatorio; vacío = no defendible).
        confidence: Confianza declarada en [0.0, 1.0].
    """

    timestamp: float
    action: str
    chosen: str
    rationale: str
    confidence: float


@dataclass(frozen=True)
class FourQuestionsReport:
    """Resultado del chequeo de las cuatro preguntas.

    Attributes:
        authority_ok: Existe kill-switch operativo.
        defense_ok: Existen decisiones registradas reconstruibles.
        visibility_ok: Existe monitor activo.
        response_ok: Existe procedimiento de incidentes completo.
        details: Detalles legibles por pregunta.
    """

    authority_ok: bool
    defense_ok: bool
    visibility_ok: bool
    response_ok: bool
    details: dict[str, str] = field(default_factory=dict)

    @property
    def all_pass(self) -> bool:
        """Indica si las cuatro preguntas pasan.

        Returns:
            True solo si autoridad, defensa, visibilidad y respuesta OK.
        """
        return (
            self.authority_ok
            and self.defense_ok
            and self.visibility_ok
            and self.response_ok
        )


class AgentGovernanceBoard:
    """Tablero de gobernanza: capacidades operativas, no políticas.

    Uso típico::

        board = AgentGovernanceBoard()
        board.register_kill_switch("builder", ops.stop_builder)
        board.register_monitor(lambda name, payload: log.info(name))
        board.register_incident_procedure(IncidentProcedure(...))
        board.record_decision("pause", "builder", "anomalía detectada", 0.9)
        report = board.run_four_questions()
        assert report.all_pass
    """

    def __init__(self) -> None:
        """Inicializa el tablero sin capacidades registradas."""
        self._kill_switches: dict[str, KillSwitch] = {}
        self._monitors: list[MonitorCallback] = []
        self._procedure: IncidentProcedure | None = None
        self._decisions: list[GovernanceDecisionRecord] = []

    # ------------------------------------------------------------------
    # Registro de capacidades
    # ------------------------------------------------------------------

    def register_kill_switch(self, target_name: str, stop_fn: KillSwitch) -> None:
        """Registra el mecanismo de pausa de un agente/sistema.

        Args:
            target_name: Nombre del agente o sistema pausable.
            stop_fn: Callable que lo detiene; True si se detuvo.
        """
        self._kill_switches[target_name] = stop_fn
        self.emit_event("kill_switch_registered", {"target": target_name})

    def register_monitor(self, callback: MonitorCallback) -> None:
        """Registra un monitor que recibirá todos los eventos.

        Args:
            callback: Callable ``(event_name, payload)``.
        """
        self._monitors.append(callback)

    def register_incident_procedure(self, procedure: IncidentProcedure) -> None:
        """Registra el procedimiento de respuesta a incidentes.

        Args:
            procedure: Procedimiento con owner, runbook y portavoz.
        """
        self._procedure = procedure

    # ------------------------------------------------------------------
    # Operación
    # ------------------------------------------------------------------

    def pause(self, target_name: str, rationale: str, confidence: float = 1.0) -> bool:
        """Pausa un agente vía su kill-switch y audita la decisión.

        Args:
            target_name: Nombre del agente/sistema a pausar.
            rationale: Motivo de la pausa (prueba de defensa).
            confidence: Confianza en la decisión [0.0, 1.0].

        Returns:
            True si el kill-switch detuvo el objetivo.

        Raises:
            KeyError: Si el objetivo no tiene kill-switch registrado.
        """
        if target_name not in self._kill_switches:
            raise KeyError(
                f"WHAT: no existe kill-switch para '{target_name}'. "
                "WHY: pausar un sistema sin mecanismo registrado viola la "
                "pregunta 1 (autoridad). "
                "WHERE: AgentGovernanceBoard.pause()"
            )
        stopped = bool(self._kill_switches[target_name](target_name))
        self.record_decision(
            action="pause",
            chosen=target_name,
            rationale=rationale,
            confidence=confidence,
        )
        self.emit_event("agent_paused", {"target": target_name, "stopped": stopped})
        return stopped

    def record_decision(
        self,
        action: str,
        chosen: str,
        rationale: str,
        confidence: float,
    ) -> GovernanceDecisionRecord:
        """Registra una decisión con su rationale (patrón BTR).

        Args:
            action: Acción ejecutada.
            chosen: Elección concreta.
            rationale: Justificación obligatoria.
            confidence: Confianza declarada [0.0, 1.0].

        Returns:
            El registro inmutable creado.

        Raises:
            ValueError: Si ``rationale`` está vacío o la confianza sale de
                rango: una decisión sin justificación no es defendible.
        """
        if not rationale.strip():
            raise ValueError(
                "WHAT: rationale vacío en decisión de gobernanza. "
                "WHY: una decisión que no se puede explicar no se puede "
                "defender (pregunta 2). "
                "WHERE: AgentGovernanceBoard.record_decision()"
            )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                f"WHAT: confianza fuera de rango ({confidence}). "
                "WHY: debe estar en [0.0, 1.0]. "
                "WHERE: AgentGovernanceBoard.record_decision()"
            )
        record = GovernanceDecisionRecord(
            timestamp=time.time(),
            action=action,
            chosen=chosen,
            rationale=rationale,
            confidence=confidence,
        )
        self._decisions.append(record)
        return record

    def emit_event(self, event_name: str, payload: dict[str, Any]) -> None:
        """Propaga un evento a todos los monitores registrados.

        Un monitor que falle NO debe romper la operación: se registra el
        error y los demás monitores siguen recibiendo eventos.

        Args:
            event_name: Nombre del evento.
            payload: Datos asociados al evento.
        """
        for monitor in self._monitors:
            try:
                monitor(event_name, payload)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Monitor de gobernanza falló para evento '%s': %s",
                    event_name,
                    exc,
                )

    # ------------------------------------------------------------------
    # Chequeo de las cuatro preguntas
    # ------------------------------------------------------------------

    def run_four_questions(self) -> FourQuestionsReport:
        """Evalúa las cuatro preguntas sobre las capacidades registradas.

        Returns:
            Reporte con el veredicto por pregunta y sus detalles.
        """
        authority_ok = len(self._kill_switches) > 0
        defense_ok = len(self._decisions) > 0
        visibility_ok = len(self._monitors) > 0
        procedure = self._procedure
        response_ok = bool(
            procedure is not None
            and procedure.owner.strip()
            and procedure.runbook_ref.strip()
            and procedure.spokesperson.strip()
        )
        return FourQuestionsReport(
            authority_ok=authority_ok,
            defense_ok=defense_ok,
            visibility_ok=visibility_ok,
            response_ok=response_ok,
            details={
                "authority": (
                    f"{len(self._kill_switches)} kill-switch(es): "
                    f"{sorted(self._kill_switches)}"
                ),
                "defense": f"{len(self._decisions)} decisión(es) auditadas",
                "visibility": f"{len(self._monitors)} monitor(es) activo(s)",
                "response": (
                    "procedimiento completo"
                    if response_ok
                    else "procedimiento ausente o incompleto"
                ),
            },
        )
