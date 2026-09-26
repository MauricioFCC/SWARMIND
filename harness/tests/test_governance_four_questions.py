"""Tests para las cuatro preguntas de gobernanza (ADR-0051).

Cubre:
- Reporte inicial: las cuatro preguntas fallan sin capacidades.
- Registro de kill-switch, monitor y procedimiento activa cada chequeo.
- Pausa con auditoría de decisión (patrón BTR).
- Errores accionables: kill-switch inexistente, rationale vacío, confianza
  fuera de rango.
- Aislamiento de monitores: un monitor que falla no rompe los demás.
"""
from __future__ import annotations

import pytest

from harness.security.governance import (
    AgentGovernanceBoard,
    IncidentProcedure,
)


@pytest.fixture
def board() -> AgentGovernanceBoard:
    """Fixture: tablero vacío sin capacidades registradas."""
    return AgentGovernanceBoard()


def _register_all(board: AgentGovernanceBoard) -> None:
    """Registra las cuatro capacidades completas en el tablero."""
    board.register_kill_switch("builder", lambda name: True)
    board.register_monitor(lambda name, payload: None)
    board.register_incident_procedure(
        IncidentProcedure(
            owner="CISO",
            runbook_ref="runbooks/ai-incident.md",
            spokesperson="Comms Lead",
        )
    )
    board.record_decision("register", "builder", "agente aprobado por comité", 0.95)


class TestFourQuestions:
    """Chequeo integral de las cuatro preguntas."""

    def test_tablero_vacio_falla_todas(self, board: AgentGovernanceBoard) -> None:
        report = board.run_four_questions()
        assert report.all_pass is False
        assert not report.authority_ok
        assert not report.defense_ok
        assert not report.visibility_ok
        assert not report.response_ok

    def test_capacidades_completas_pasan_todas(self, board: AgentGovernanceBoard) -> None:
        _register_all(board)
        report = board.run_four_questions()
        assert report.all_pass is True

    def test_sin_procedimiento_respuesta_falla(self, board: AgentGovernanceBoard) -> None:
        board.register_kill_switch("builder", lambda name: True)
        board.register_monitor(lambda name, payload: None)
        board.record_decision("x", "y", "razón", 0.5)
        assert board.run_four_questions().response_ok is False


class TestPause:
    """Pausa vía kill-switch con auditoría."""

    def test_pause_invoca_kill_switch_y_audita(self, board: AgentGovernanceBoard) -> None:
        calls: list[str] = []

        def stop(target: str) -> bool:
            """Kill-switch de prueba que registra y confirma la parada."""
            calls.append(target)
            return True

        board.register_kill_switch("builder", stop)
        stopped = board.pause("builder", "anomalía detectada", 0.9)
        assert stopped is True
        assert calls == ["builder"]
        trail = board._decisions
        assert len(trail) == 1
        assert trail[0].action == "pause"
        assert trail[0].rationale == "anomalía detectada"

    def test_pause_sin_kill_switch_lanza_keyerror(self, board: AgentGovernanceBoard) -> None:
        with pytest.raises(KeyError, match="kill-switch"):
            board.pause("fantasma", "motivo")

    def test_rationale_vacio_rechazado(self, board: AgentGovernanceBoard) -> None:
        with pytest.raises(ValueError, match="rationale vacío"):
            board.record_decision("pause", "builder", "   ", 0.9)

    def test_confianza_fuera_de_rango_rechazada(self, board: AgentGovernanceBoard) -> None:
        with pytest.raises(ValueError, match="confianza fuera de rango"):
            board.record_decision("pause", "builder", "motivo", 1.5)


class TestMonitors:
    """Visibilidad: propagación de eventos a monitores."""

    def test_eventos_llegan_a_monitores(self, board: AgentGovernanceBoard) -> None:
        received: list[tuple[str, dict]] = []
        board.register_monitor(lambda name, payload: received.append((name, payload)))
        board.emit_event("test_event", {"k": 1})
        assert received == [("test_event", {"k": 1})]

    def test_monitor_roto_no_rompe_los_demas(self, board: AgentGovernanceBoard) -> None:
        def broken(name: str, payload: dict) -> None:
            raise RuntimeError("monitor caído")

        received: list[str] = []
        board.register_monitor(broken)
        board.register_monitor(lambda name, payload: received.append(name))
        board.emit_event("evt", {})
        assert received == ["evt"]  # el segundo monitor sí recibió el evento
