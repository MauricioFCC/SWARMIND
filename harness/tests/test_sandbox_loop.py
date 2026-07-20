"""
Tests para SandboxLoop — bucle autonomo de calidad para codigo generado.

Cubre: execute_cycle (exito/fallo/circuit breaker/exception),
run_autonomous (codigo vacio, exito, iteraciones, escalacion),
notificaciones internas, get_status.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

from harness.orchestrator.sandbox_loop import SandboxLoop, _DEFAULT_MAX_ITERATIONS
from harness.tools_sandbox.mcp_executor import SandboxResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_vector_store():
    """Vector store simulado."""
    store = MagicMock()
    store.search.return_value = []
    return store


@pytest.fixture
def mock_agent_bus():
    """AgentBus simulado."""
    bus = MagicMock()
    bus.count_iterations.return_value = 0
    bus.check_circuit_breaker.return_value = False
    bus.post_message.return_value = "msg-123"
    return bus


@pytest.fixture
def mock_executor():
    """MCPExecutor simulado."""
    executor = MagicMock()
    executor.run_test.return_value = SandboxResult(
        success=True,
        output="tests passed",
        error="",
        execution_time=1.23,
    )
    return executor


@pytest.fixture
def mock_cognition():
    """CognitionSync simulado."""
    return MagicMock()


@pytest.fixture
def sandbox_loop(mock_vector_store, mock_agent_bus, mock_executor, mock_cognition):
    """SandboxLoop con todas las dependencias mockeadas."""
    # Conectar bus.store al mismo mock que store para get_status
    mock_agent_bus.store = mock_vector_store
    return SandboxLoop(
        vector_store=mock_vector_store,
        agent_bus=mock_agent_bus,
        executor=mock_executor,
        cognition=mock_cognition,
    )


@pytest.fixture
def fail_result() -> SandboxResult:
    """Resultado de test fallido."""
    return SandboxResult(
        success=False,
        output="",
        error="AssertionError: assert 1 == 2",
        execution_time=0.5,
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    """Tests del constructor."""

    def test_default_construction(self):
        """Debe crear instancias por defecto si no se pasan."""
        from unittest.mock import MagicMock
        with patch("harness.orchestrator.sandbox_loop.LanceVectorStore") as mock_store:
            with patch("harness.orchestrator.sandbox_loop.AgentBus") as mock_bus:
                with patch("harness.orchestrator.sandbox_loop.MCPExecutor") as mock_exec:
                    with patch("harness.orchestrator.sandbox_loop.CognitionSync") as mock_cog:
                        loop = SandboxLoop()
        assert loop.store is not None
        assert loop.bus is not None
        assert loop.executor is not None
        assert loop.cognition is not None

    def test_custom_dependencies(self, mock_vector_store, mock_agent_bus,
                                 mock_executor, mock_cognition):
        """Debe usar las dependencias inyectadas."""
        loop = SandboxLoop(
            vector_store=mock_vector_store,
            agent_bus=mock_agent_bus,
            executor=mock_executor,
            cognition=mock_cognition,
        )
        assert loop.store is mock_vector_store
        assert loop.bus is mock_agent_bus
        assert loop.executor is mock_executor
        assert loop.cognition is mock_cognition


# ---------------------------------------------------------------------------
# execute_cycle
# ---------------------------------------------------------------------------


class TestExecuteCycle:
    """Tests para execute_cycle."""

    def test_success_notifies_quality_gate(self, sandbox_loop, mock_agent_bus):
        """Tests pasan → debe notificar a @quality-gate."""
        exito, resultado = sandbox_loop.execute_cycle(
            task_description="test task",
            code="def test_foo(): pass",
        )
        assert exito is True
        assert resultado.success is True
        mock_agent_bus.post_message.assert_called_once()
        call_args = mock_agent_bus.post_message.call_args[1]
        assert call_args["to_agent"] == "@quality-gate"
        assert call_args["message_type"] == "response"

    def test_failure_notifies_engineer(self, sandbox_loop, mock_executor,
                                       mock_agent_bus, fail_result):
        """Tests fallan → debe notificar a @software-engineer."""
        mock_executor.run_test.return_value = fail_result
        exito, resultado = sandbox_loop.execute_cycle(
            task_description="test task",
            code="def test_foo(): assert False",
            task_id="task-1",
        )
        assert exito is False
        assert resultado.success is False
        # Debe haber llamado a post_message al menos una vez (para engineer)
        engineer_calls = [
            c for c in mock_agent_bus.post_message.call_args_list
            if c[1].get("to_agent") == "@software-engineer"
        ]
        assert len(engineer_calls) >= 1

    def test_failure_counts_iterations(self, sandbox_loop, mock_executor,
                                       mock_agent_bus, fail_result):
        """Debe contar iteraciones via AgentBus."""
        mock_executor.run_test.return_value = fail_result
        mock_agent_bus.count_iterations.return_value = 2
        sandbox_loop.execute_cycle(
            task_description="test",
            code="bad code",
            task_id="task-1",
        )
        mock_agent_bus.count_iterations.assert_called_with("task-1")

    def test_circuit_breaker_triggers_escalation(self, sandbox_loop, mock_executor,
                                                  mock_agent_bus, mock_cognition,
                                                  fail_result):
        """Circuit breaker disparado → debe escalar a humano."""
        mock_executor.run_test.return_value = fail_result
        mock_agent_bus.check_circuit_breaker.return_value = True
        sandbox_loop.execute_cycle(
            task_description="test",
            code="bad code",
            task_id="task-1",
        )
        # Debe haber escalado a @human
        escalation_calls = [
            c for c in mock_agent_bus.post_message.call_args_list
            if c[1].get("to_agent") == "@human"
        ]
        assert len(escalation_calls) >= 1
        # Debe haber registrado leccion
        mock_cognition.add_lesson.assert_called_once()

    def test_circuit_breaker_not_triggered_without_task_id(self, sandbox_loop,
                                                            mock_executor,
                                                            mock_agent_bus,
                                                            fail_result):
        """Sin task_id, no debe verificar circuit breaker."""
        mock_executor.run_test.return_value = fail_result
        sandbox_loop.execute_cycle(
            task_description="test",
            code="bad code",
        )
        mock_agent_bus.check_circuit_breaker.assert_not_called()

    def test_executor_exception_handled(self, sandbox_loop, mock_executor):
        """Excepcion en executor debe capturarse y retornar resultado de error."""
        mock_executor.run_test.side_effect = RuntimeError("sandbox crash")
        exito, resultado = sandbox_loop.execute_cycle(
            task_description="test",
            code="code",
            task_id="task-1",
        )
        assert exito is False
        assert resultado.success is False
        assert "Error en el sandbox executor" in resultado.error

    def test_executor_exception_circuit_breaker(self, sandbox_loop, mock_executor,
                                                 mock_agent_bus, mock_cognition):
        """Excepcion en executor + circuit breaker debe escalar."""
        mock_executor.run_test.side_effect = RuntimeError("crash")
        mock_agent_bus.check_circuit_breaker.return_value = True
        sandbox_loop.execute_cycle(
            task_description="test",
            code="code",
            task_id="task-1",
        )
        mock_cognition.add_lesson.assert_called_once()

    def test_success_without_task_id(self, sandbox_loop):
        """Sin task_id, exito debe funcionar igual."""
        exito, resultado = sandbox_loop.execute_cycle(
            task_description="test",
            code="code",
        )
        assert exito is True


# ---------------------------------------------------------------------------
# run_autonomous
# ---------------------------------------------------------------------------


class TestRunAutonomous:
    """Tests para run_autonomous."""

    def test_empty_code_returns_false(self, sandbox_loop, mock_agent_bus):
        """Codigo vacio debe retornar (False, None) y notificar."""
        exito, resultado = sandbox_loop.run_autonomous(
            task_id="task-1",
            code="",
        )
        assert exito is False
        assert resultado is None
        mock_agent_bus.post_message.assert_called_once()
        call_args = mock_agent_bus.post_message.call_args[1]
        assert call_args["to_agent"] == "@software-engineer"

    def test_success_first_iteration(self, sandbox_loop):
        """Exito en primera iteracion debe retornar (True, resultado)."""
        exito, resultado = sandbox_loop.run_autonomous(
            task_id="task-1",
            code="def test(): pass",
            max_iterations=3,
        )
        assert exito is True
        assert resultado is not None
        assert resultado.success is True

    def test_max_iterations_reached(self, sandbox_loop, mock_executor,
                                     mock_agent_bus, mock_cognition, fail_result):
        """Debe iterar hasta max_iterations si siempre falla."""
        mock_executor.run_test.return_value = fail_result
        mock_agent_bus.check_circuit_breaker.return_value = False

        exito, resultado = sandbox_loop.run_autonomous(
            task_id="task-1",
            code="bad code",
            max_iterations=3,
        )
        assert exito is False
        assert resultado is not None
        # Debe haber ejecutado 3 ciclos
        assert mock_executor.run_test.call_count == 3
        # Debe haber escalado al final
        mock_cognition.add_lesson.assert_called_once()

    def test_circuit_breaker_mid_loop(self, sandbox_loop, mock_executor,
                                       mock_agent_bus, fail_result):
        """Circuit breaker disparado durante el loop debe detener iteraciones."""
        mock_executor.run_test.return_value = fail_result
        # execute_cycle llama a check_circuit_breaker -> False (no break ahi)
        # Luego run_autonomous vuelve a llamar -> True (break)
        mock_agent_bus.check_circuit_breaker.side_effect = [False, True]

        exito, resultado = sandbox_loop.run_autonomous(
            task_id="task-1",
            code="bad code",
            max_iterations=5,
        )
        assert exito is False
        # Solo 1 ciclo: execute_cycle no activa CB, pero run_autonomous detecta CB post-ciclo
        assert mock_executor.run_test.call_count == 1

    def test_success_on_second_iteration(self, sandbox_loop, mock_executor, fail_result):
        """Exito en segunda iteracion debe retornar True."""
        success_result = SandboxResult(
            success=True, output="ok", error="", execution_time=0.5,
        )
        mock_executor.run_test.side_effect = [fail_result, success_result]

        exito, resultado = sandbox_loop.run_autonomous(
            task_id="task-1",
            code="code",
            max_iterations=3,
        )
        assert exito is True
        assert mock_executor.run_test.call_count == 2


# ---------------------------------------------------------------------------
# _notify_quality_gate
# ---------------------------------------------------------------------------


class TestNotifyQualityGate:
    """Tests para _notify_quality_gate."""

    def test_sends_correct_message(self, sandbox_loop, mock_agent_bus):
        """Debe enviar mensaje a @quality-gate con el formato correcto."""
        sandbox_loop._notify_quality_gate(
            channel="#swe-sandbox",
            task_description="Implement API",
            task_id="t-1",
            code="def test(): pass",
            output="3 passed",
            execution_time=1.5,
        )
        mock_agent_bus.post_message.assert_called_once()
        args = mock_agent_bus.post_message.call_args[1]
        assert args["to_agent"] == "@quality-gate"
        assert args["message_type"] == "response"
        assert "Implement API" in args["message"]
        assert args["attachments"] == ["def test(): pass"]

    def test_without_code(self, sandbox_loop, mock_agent_bus):
        """Sin codigo, attachments debe ser None."""
        sandbox_loop._notify_quality_gate(
            channel="#ch",
            task_description="t",
            task_id=None,
            code="",
            output="ok",
            execution_time=0.5,
        )
        args = mock_agent_bus.post_message.call_args[1]
        assert args["attachments"] is None


# ---------------------------------------------------------------------------
# _notify_software_engineer
# ---------------------------------------------------------------------------


class TestNotifySoftwareEngineer:
    """Tests para _notify_software_engineer."""

    def test_sends_correct_message(self, sandbox_loop, mock_agent_bus):
        """Debe enviar mensaje a @software-engineer con error."""
        sandbox_loop._notify_software_engineer(
            channel="#swe-sandbox",
            task_description="Implement API",
            task_id="t-1",
            code="code",
            iteration=2,
            error="AssertionError",
            execution_time=1.5,
        )
        args = mock_agent_bus.post_message.call_args[1]
        assert args["to_agent"] == "@software-engineer"
        assert args["message_type"] == "error"
        assert args["iteration"] == 2


# ---------------------------------------------------------------------------
# _handle_escalation
# ---------------------------------------------------------------------------


class TestHandleEscalation:
    """Tests para _handle_escalation."""

    def test_sends_escalation_message(self, sandbox_loop, mock_agent_bus):
        """Debe enviar mensaje de escalacion a @human."""
        sandbox_loop._handle_escalation(
            task_id="t-1",
            task_description="Task t-1",
            code="code",
            iteration=3,
            last_error="crash",
            channel="#escalations",
        )
        human_calls = [
            c for c in mock_agent_bus.post_message.call_args_list
            if c[1].get("to_agent") == "@human"
        ]
        assert len(human_calls) >= 1
        assert "CIRCUIT BREAKER" in human_calls[0][1]["message"]

    def test_registers_lesson(self, sandbox_loop, mock_cognition):
        """Debe registrar leccion en cognition store."""
        sandbox_loop._handle_escalation(
            task_id="t-1",
            task_description="Task t-1",
            code="code",
            iteration=3,
            last_error="error details",
            channel="#ch",
        )
        mock_cognition.add_lesson.assert_called_once()
        args = mock_cognition.add_lesson.call_args[1]
        assert args["domain"] == "harness.sandbox"
        assert "circuit-breaker" in args["tags"]

    def test_cognition_exception_handled(self, sandbox_loop, mock_cognition):
        """Excepcion en cognition.add_lesson no debe propagarse."""
        mock_cognition.add_lesson.side_effect = RuntimeError("store down")
        sandbox_loop._handle_escalation(
            task_id="t-1",
            task_description="Task",
            code="code",
            iteration=1,
            last_error="err",
            channel="#ch",
        )
        # No debe lanzar excepcion


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    """Tests para get_status."""

    def test_returns_status_dict(self, sandbox_loop, mock_agent_bus):
        """Debe retornar dict con estado de la tarea."""
        mock_agent_bus.count_iterations.return_value = 2
        mock_agent_bus.check_circuit_breaker.return_value = False
        status = sandbox_loop.get_status("task-1")
        assert status["task_id"] == "task-1"
        assert status["error_count"] == 2
        assert status["circuit_breaker_open"] is False
        assert status["max_iterations"] == _DEFAULT_MAX_ITERATIONS

    def test_search_exception_handled(self, sandbox_loop, mock_vector_store):
        """Excepcion en busqueda debe manejarse sin propagar."""
        mock_vector_store.search.side_effect = RuntimeError("search failed")
        status = sandbox_loop.get_status("task-1")
        assert status["task_id"] == "task-1"
        assert status["ultimo_mensaje"] is None

    def test_no_results_returns_none(self, sandbox_loop, mock_vector_store):
        """Sin resultados, ultimo_mensaje debe ser None."""
        mock_vector_store.search.return_value = []
        status = sandbox_loop.get_status("task-1")
        assert status["ultimo_mensaje"] is None

    def test_with_message_result(self, sandbox_loop, mock_vector_store, mock_agent_bus):
        """Con resultados, debe deserializar ultimo mensaje."""
        mock_vector_store.search.return_value = [
            {"metadata": {"task_id": "task-1"}, "score": 0.9}
        ]
        mock_agent_bus._deserialize_message.return_value = {
            "content": "test msg", "role": "assistant"
        }
        status = sandbox_loop.get_status("task-1")
        assert status["ultimo_mensaje"] is not None
        assert status["ultimo_mensaje"]["content"] == "test msg"
        assert "vector" not in status["ultimo_mensaje"]
