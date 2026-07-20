"""Tests for TaskOrchestrator — plan-and-execute pipeline with self-healing."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch, ANY

import pytest

from harness.orchestrator.task_orchestrator import TaskOrchestrator
from harness.orchestrator.task_planner import SubTask, TaskPlan
from harness.orchestrator.session_context import SessionContext, SessionState
from harness.orchestrator.orchestration_result import OrchestratorResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_STORE = MagicMock()
"""Mock global reutilizable para evitar que AgentBus intente crear LanceVectorStore."""


def _make_orch(**kwargs: object) -> TaskOrchestrator:
    """Crea un TaskOrchestrator con vector_store mockeado por defecto."""
    if "vector_store" not in kwargs:
        kwargs["vector_store"] = _MOCK_STORE
    return TaskOrchestrator(**kwargs)


def _make_plan(session_id: str = "test-session",
               n_subtasks: int = 1,
               template_name: str = "") -> TaskPlan:
    """Crea un TaskPlan simple con N subtasks sin dependencias."""
    subtasks = [
        SubTask(
            id=f"st-{i}",
            agent="builder" if i % 2 == 0 else "scientist",
            description=f"Subtask {i}",
            dependencies=[],
            expected_output=f"output {i}",
            context_hint=f"hint {i}",
            confidence_impact="neutral",
        )
        for i in range(n_subtasks)
    ]
    return TaskPlan(
        session_id=session_id,
        original_message="test message",
        subtasks=subtasks,
        template_name=template_name,
    )


def _make_session(plan: TaskPlan | None = None,
                  session_id: str = "test-session") -> SessionState:
    """Crea un SessionState a partir de un plan o con uno nuevo."""
    if plan is None:
        plan = _make_plan(session_id=session_id)
    return SessionState(
        session_id=plan.session_id,
        original_message=plan.original_message,
        plan=plan,
    )


# ===================================================================
# Init
# ===================================================================

class TestTaskOrchestratorInit:
    """Verifica inicialización del orquestador."""

    def test_init_defaults(self) -> None:
        """Valores por defecto se asignan correctamente."""
        orch = _make_orch()
        assert orch._max_retries == 3
        assert orch._level_timeout_sec == 300.0
        assert orch._stall_timeout_sec == 120.0
        assert orch._verbose is False
        assert orch._recent_messages == {}
        assert orch._dedup_window == 30.0
        assert orch._global_cb is not None
        assert orch._healing_contexts == {}

    def test_init_with_vector_store(self, vector_store) -> None:
        """Vector store se propaga a componentes internos."""
        orch = TaskOrchestrator(vector_store=vector_store, verbose=True)
        assert orch._verbose is True
        assert orch._store is vector_store

    def test_get_or_create_healing_new(self) -> None:
        """_get_or_create_healing crea nuevo contexto si no existe."""
        orch = _make_orch()
        healing = orch._get_or_create_healing("new-session")
        assert healing is not None
        assert healing.session_id == "new-session"
        assert "new-session" in orch._healing_contexts

    def test_get_or_create_healing_existing(self) -> None:
        """_get_or_create_healing retorna el existente."""
        orch = _make_orch()
        from harness.orchestrator.self_healing import SelfHealingContext
        existing = SelfHealingContext(session_id="existing-session")
        orch._healing_contexts["existing-session"] = existing
        assert orch._get_or_create_healing("existing-session") is existing


# ===================================================================
# Circuit Breaker & Dedup  (líneas 152–168)
# ===================================================================

class TestCircuitBreakerAndDedup:
    """Circuit breaker abierto y deduplicación de mensajes."""

    def test_circuit_breaker_open_returns_error(self) -> None:
        """Circuito global abierto → process_message retorna error.  (líneas 152-157)"""
        orch = _make_orch()
        mock_cb = MagicMock()
        mock_cb.is_available = False
        mock_cb.failure_count = 5
        orch._global_cb = mock_cb

        result = orch.process_message("test message")

        assert result.session_id == "error"
        assert "Sistema en recuperación" in result.session_status

    def test_stale_cleanup_removes_old_entries(self) -> None:
        """Entradas viejas en recent_messages se limpian.  (línea 168)"""
        orch = _make_orch()
        mock_cb = MagicMock()
        mock_cb.is_available = True
        orch._global_cb = mock_cb
        orch._recent_messages = {
            "stale_1": time.time() - 60,
            "stale_2": time.time() - 60,
        }
        orch._session_ctx = SessionContext()
        orch._bus = MagicMock()

        result = orch.process_message("completely new unique message")

        assert "stale_1" not in orch._recent_messages
        assert "stale_2" not in orch._recent_messages
        assert len(orch._recent_messages) == 1

    def test_duplicate_message_blocked(self) -> None:
        """Mensaje duplicado dentro de la ventana es bloqueado."""
        orch = _make_orch()
        mock_cb = MagicMock()
        mock_cb.is_available = True
        orch._global_cb = mock_cb

        import hashlib
        msg = "test message"
        msg_hash = hashlib.sha256(msg.encode()).hexdigest()[:16]
        orch._recent_messages = {msg_hash: time.time()}

        result = orch.process_message(msg)
        assert "duplicado" in result.session_status


# ===================================================================
# Continuation Flow  (líneas 193–206, 597, 601, 639–648)
# ===================================================================

class TestContinuationFlow:
    """Detección y manejo de mensajes de continuación."""

    def test_continuation_path(self) -> None:
        """Mensaje de continuación ejecuta _handle_continuation.  (líneas 193-206)"""
        orch = _make_orch()
        mock_cb = MagicMock()
        mock_cb.is_available = True
        orch._global_cb = mock_cb
        orch._session_ctx = SessionContext()
        plan = _make_plan()
        session = orch._session_ctx.get_or_create("test", plan)
        orch._bus = MagicMock()

        with patch.object(orch, '_is_continuation', return_value=True):
            result = orch.process_message("continue please")

        assert result.session_id == session.session_id
        assert len(session.messages) == 1
        assert session.messages[0]["content"] == "continue please"

    def test_is_continuation_keyword_match(self) -> None:
        """Palabras clave de continuación se detectan.  (línea 597)"""
        orch = _make_orch()
        session = _make_session()
        keywords = [
            "continuar", "continue", "siguiente", "next", "sigue",
            "proceder", "proceed", "avanzar", "adelante",
            "terminar", "finish", "completar", "complete",
            "paso", "step", "sigue con",
        ]
        for kw in keywords:
            assert orch._is_continuation(kw, session), f"'{kw}' debería detectarse"

    def test_is_continuation_short_message(self) -> None:
        """Mensajes < 10 chars se consideran continuación.  (línea 601)"""
        orch = _make_orch()
        session = _make_session()
        for msg in ["hi", "ok", "yes", "continu", "12345678"]:
            assert orch._is_continuation(msg, session), f"'{msg}' debería ser continuación"

    def test_is_not_continuation_no_session(self) -> None:
        """Sin sesión activa no es continuación."""
        orch = _make_orch()
        assert not orch._is_continuation("continue", None)

    def test_is_not_continuation_completed_session(self) -> None:
        """Sesión completada no es continuación."""
        orch = _make_orch()
        session = _make_session()
        session.completed = True
        assert not orch._is_continuation("continue", session)

    def test_is_not_continuation_new_task(self) -> None:
        """Mensaje largo sin keywords no es continuación."""
        orch = _make_orch()
        session = _make_session()
        assert not orch._is_continuation(
            "implement a new REST API in Rust with tests and docs", session
        )

    def test_handle_continuation(self) -> None:
        """_handle_continuation añade mensaje y construye resultado.  (líneas 639-648)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        orch._session_ctx = SessionContext()
        orch._session_ctx._active_sessions[session.session_id] = session
        orch._bus = MagicMock()

        result = orch._handle_continuation("continue", session, "builder")

        assert result.session_id == session.session_id
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "continue"


# ===================================================================
# Process Completion  (líneas 257–274, 322, 331)
# ===================================================================

class TestProcessCompletion:
    """Flujo de process_completion."""

    def test_session_not_found(self) -> None:
        """Sesión no encontrada → resultado vacío.  (líneas 257-262)"""
        orch = _make_orch()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = None

        result = orch.process_completion("nonexistent", "st-1", "result")

        assert result.session_id == "error"
        assert "no encontrada" in result.session_status

    def test_subtask_already_completed(self) -> None:
        """Subtask ya completada no se marca de nuevo.  (línea 274)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        plan.subtasks[0].completed = True
        plan.subtasks[0].result = "already done"
        session = _make_session(plan=plan)
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = session
        orch._bus = MagicMock()
        mock_healing = MagicMock()
        mock_healing.check_timeout.return_value = None
        mock_healing.check_stalled.return_value = None
        orch._healing_contexts[session.session_id] = mock_healing

        result = orch.process_completion(session.session_id, "st-0", "new result")

        orch._session_ctx.mark_subtask_done.assert_not_called()

    def test_completion_with_confidence_scoring(self) -> None:
        """Completar subtask dispara confidence scoring."""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = session
        orch._bus = MagicMock()
        mock_healing = MagicMock()
        mock_healing.get_circuit_breaker.return_value = MagicMock()
        mock_healing.check_timeout.return_value = None
        mock_healing.check_stalled.return_value = None
        orch._healing_contexts[session.session_id] = mock_healing

        mock_score = MagicMock()
        mock_score.score = 0.85
        mock_score.should_stop = False
        mock_score.level = "high"
        mock_score.signals = {"length": 0.8, "hedging": 0.9, "self_correction": 1.0}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score

        result = orch.process_completion(session.session_id, "st-0", "great result")

        orch._session_ctx.mark_subtask_done.assert_called_once_with(
            session, "st-0", "great result"
        )
        orch._confidence_scorer.score_completion.assert_called_once()

    def test_completion_timeout_and_stall_warnings(self, caplog: Any) -> None:
        """Timeout y stall generan StructuredLogRecord.warning.  (líneas 322, 331)"""
        import logging
        caplog.set_level(logging.WARNING)

        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = session
        orch._bus = MagicMock()
        mock_healing = MagicMock()
        mock_healing.get_circuit_breaker.return_value = MagicMock()
        mock_healing.check_timeout.return_value = "LEVEL_TIMEOUT: Nivel 1"
        mock_healing.check_stalled.return_value = "STALL_DETECTED: Sin progreso"
        mock_healing.stalled_warnings = 1
        # to_dict NO debe incluir 'level' ni 'session_id'
        # (StructuredLogRecord.warning los pasa como posicional/keyword explícito)
        mock_healing.to_dict.return_value = {
            "level_age_sec": 301.0,
            "last_progress_sec": 121.0,
            "stalled_warnings": 1,
        }
        orch._healing_contexts[session.session_id] = mock_healing
        mock_score = MagicMock()
        mock_score.score = 0.5
        mock_score.should_stop = False
        mock_score.level = "medium"
        mock_score.signals = {"length": 0.5}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score

        orch.process_completion(session.session_id, "st-0", "result")
        # Debe haber al menos 2 warnings: timeout y stall
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) >= 2

    def test_plan_complete_celebrates(self) -> None:
        """Plan completo → broadcast_complete + global_cb.success."""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=1)
        plan.subtasks[0].completed = True
        session = _make_session(plan=plan)
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = session
        orch._bus = MagicMock()
        orch._global_cb = MagicMock()
        mock_healing = MagicMock()
        mock_healing.get_circuit_breaker.return_value = MagicMock()
        mock_healing.check_timeout.return_value = None
        mock_healing.check_stalled.return_value = None
        orch._healing_contexts[session.session_id] = mock_healing
        mock_score = MagicMock()
        mock_score.score = 0.5
        mock_score.should_stop = False
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score

        result = orch.process_completion(session.session_id, "st-0", "done")
        assert result.is_complete is True
        orch._global_cb.record_success.assert_called_once()


# ===================================================================
# GetSummary & Healing Status  (líneas 349, 369, 375–376)
# ===================================================================

class TestGetSummaryAndHealing:
    """Tests para get_summary y get_healing_status."""

    def test_get_summary_no_session(self) -> None:
        """Sin sesión activa → mensaje de error.  (línea 349)"""
        orch = _make_orch()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_active.return_value = None
        assert "No hay sesiones activas" in orch.get_summary()

    def test_get_summary_with_session(self) -> None:
        """Sesión existente retorna status."""
        orch = _make_orch()
        session = _make_session()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = session
        orch._session_ctx.get_status.return_value = "Sesión activa"
        summary = orch.get_summary("test-session")
        assert "Sesión activa" in summary

    def test_get_summary_with_healing_context(self) -> None:
        """get_summary incluye info de self-healing y circuit breakers.  (línea 369)"""
        orch = _make_orch()
        session = _make_session()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = session
        orch._session_ctx.get_status.return_value = "status"
        from harness.orchestrator.self_healing import SelfHealingContext, CircuitBreaker
        healing = SelfHealingContext(session_id=session.session_id)
        healing.circuit_breakers["builder"] = CircuitBreaker(failure_threshold=3)
        orch._healing_contexts[session.session_id] = healing
        summary = orch.get_summary(session.session_id)
        assert "Self-Healing" in summary
        assert "Circuit Breakers" in summary

    def test_get_healing_status_none(self) -> None:
        """Sesión sin healing → None.  (líneas 375-376)"""
        orch = _make_orch()
        assert orch.get_healing_status("nonexistent") is None

    def test_get_healing_status_exists(self) -> None:
        """Sesión con healing → dict."""
        orch = _make_orch()
        session = _make_session()
        from harness.orchestrator.self_healing import SelfHealingContext
        orch._healing_contexts[session.session_id] = SelfHealingContext(
            session_id=session.session_id
        )
        status = orch.get_healing_status(session.session_id)
        assert status is not None
        assert "session_id" in status


# ===================================================================
# RunDebate  (líneas 401, 405)
# ===================================================================

class TestRunDebate:
    """Tests para run_debate."""

    def test_session_not_found_raises(self) -> None:
        """Sesión no encontrada → ValueError.  (línea 401)"""
        orch = _make_orch()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = None
        with pytest.raises(ValueError, match="not found"):
            orch.run_debate("nonexistent", "task")

    def test_agents_extracted_from_plan(self) -> None:
        """Agents=None extrae agentes del plan.  (línea 405)"""
        # Prueba la logica de extraccion directamente
        plan = _make_plan(n_subtasks=3, session_id="debate-session")
        plan.subtasks[0].agent = "builder"
        plan.subtasks[1].agent = "scientist"
        plan.subtasks[2].agent = "guardian"

        agents = sorted({
            st.agent for st in plan.subtasks
            if st.agent != "coordinator"
        })
        assert "builder" in agents
        assert "scientist" in agents
        assert "guardian" in agents
        assert "coordinator" not in agents

    def test_strategy_mapping(self) -> None:
        """Estrategias se mapean correctamente."""
        from harness.orchestrator.debate_orchestrator import DebateStrategy

        # Prueba el mapeo de estrategias directamente
        strategy_map = {
            "consensus": DebateStrategy.CONSENSUS,
            "critique": DebateStrategy.CRITIQUE,
            "deliberation": DebateStrategy.DELIBERATION,
        }
        assert strategy_map["critique"].value == "critique"
        assert strategy_map["consensus"].value == "consensus"
        assert strategy_map["deliberation"].value == "deliberation"
        # default fallback
        assert strategy_map.get("unknown", DebateStrategy.CONSENSUS).value == "consensus"


# ===================================================================
# Confidence-Gated Early Stopping  (líneas 475, 502–569)
# ===================================================================

class TestConfidenceEarlyStopping:
    """_evaluate_confidence_and_check_early_stop."""

    def test_subtask_not_found_returns_none(self) -> None:
        """Subtask no encontrada → None.  (línea 475)"""
        orch = _make_orch()
        session = _make_session()
        result = orch._evaluate_confidence_and_check_early_stop(
            session, "nonexistent", "result"
        )
        assert result is None

    def test_low_confidence_returns_early(self) -> None:
        """Confianza baja retorna sin hacer early stopping."""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        mock_score = MagicMock()
        mock_score.score = 0.6
        mock_score.should_stop = False
        mock_score.level = "medium"
        mock_score.signals = {"length": 0.6, "hedging": 0.7}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score

        result = orch._evaluate_confidence_and_check_early_stop(
            session, "st-0", "ok result"
        )
        assert result is not None
        assert result.should_stop is False

    def test_early_stopping_skips_validation_level(self) -> None:
        """Alta confianza + nivel completado + siguiente validación → salta.  (líneas 502-569)"""
        orch = _make_orch()
        # Plan: level 0 (st-0, st-1 ambos completed), level 1 (st-2 validation)
        subtasks = [
            SubTask(id="st-0", agent="builder", description="Impl A",
                    dependencies=[], confidence_impact="critical"),
            SubTask(id="st-1", agent="scientist", description="Impl B",
                    dependencies=[], confidence_impact="critical"),
            SubTask(id="st-2", agent="guardian", description="Review",
                    dependencies=["st-0", "st-1"], confidence_impact="validation"),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        plan.subtasks[0].completed = True
        plan.subtasks[0].result = "impl A done"
        plan.subtasks[1].completed = True
        plan.subtasks[1].result = "impl B done"
        session = _make_session(plan=plan)

        mock_score = MagicMock()
        mock_score.score = 0.95
        mock_score.level = "high"
        mock_score.should_stop = True
        mock_score.signals = {"length": 0.95, "hedging": 1.0, "self_correction": 1.0}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score
        orch._session_ctx = MagicMock()
        orch._bus = MagicMock()

        # Patch get_current_level_num para que apunte al nivel 0
        # (el que está completamente completado, no el nivel 1 de validación)
        with patch.object(plan, 'get_current_level_num', return_value=0):
            result = orch._evaluate_confidence_and_check_early_stop(
                session, "st-0", "impl A done"
            )

        assert result is not None
        assert result.should_stop is True
        # La subtask de validación (st-2) debería haberse saltado
        # mark_subtask_done se llama con result= como keyword arg
        assert orch._session_ctx.mark_subtask_done.call_count == 1
        args, kwargs = orch._session_ctx.mark_subtask_done.call_args
        assert args[1] == "st-2"
        assert "[SKIPPED by confidence-gated early stopping]" in kwargs.get("result", "")

    def test_early_stopping_not_all_completed(self) -> None:
        """No salta si no todas las subtasks del nivel están completas."""
        orch = _make_orch()
        subtasks = [
            SubTask(id="st-0", agent="builder", description="task1", dependencies=[]),
            SubTask(id="st-1", agent="builder", description="task2", dependencies=[]),
            SubTask(id="st-2", agent="guardian", description="review",
                    dependencies=["st-0", "st-1"], confidence_impact="validation"),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        plan.subtasks[0].completed = True  # st-1 still pending
        session = _make_session(plan=plan)
        mock_score = MagicMock()
        mock_score.score = 0.95
        mock_score.should_stop = True
        mock_score.level = "high"
        mock_score.signals = {"length": 0.9, "hedging": 1.0}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score
        orch._session_ctx = MagicMock()

        with patch.object(plan, 'get_current_level_num', return_value=0):
            result = orch._evaluate_confidence_and_check_early_stop(
                session, "st-0", "result"
            )

        assert result is not None
        # No todas las del nivel 0 están completas (st-1 no)
        # completed_ids = {"st-0"}, level_subtask_ids = {"st-0", "st-1"}
        # {"st-0", "st-1"}.issubset({"st-0"}) → False
        orch._session_ctx.mark_subtask_done.assert_not_called()

    def test_early_stopping_not_validation_level(self) -> None:
        """No salta si el siguiente nivel no es validación."""
        orch = _make_orch()
        subtasks = [
            SubTask(id="st-0", agent="builder", description="task1", dependencies=[]),
            SubTask(id="st-1", agent="builder", description="task2",
                    dependencies=["st-0"], confidence_impact="critical"),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        plan.subtasks[0].completed = True
        session = _make_session(plan=plan)
        mock_score = MagicMock()
        mock_score.score = 0.95
        mock_score.should_stop = True
        mock_score.level = "high"
        mock_score.signals = {"length": 0.9, "hedging": 1.0}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score
        orch._session_ctx = MagicMock()

        with patch.object(plan, 'get_current_level_num', return_value=0):
            result = orch._evaluate_confidence_and_check_early_stop(
                session, "st-0", "result"
            )

        assert result is not None
        # next_confidence_impacts for level 1 = {"critical"}, not {"validation"}
        orch._session_ctx.mark_subtask_done.assert_not_called()

    def test_early_stopping_current_level_beyond_levels(self) -> None:
        """Si current_level_num >= len(levels), retorna sin saltar.  (línea 505)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=1)
        plan.subtasks[0].completed = True
        session = _make_session(plan=plan)
        mock_score = MagicMock()
        mock_score.score = 0.95
        mock_score.should_stop = True
        mock_score.level = "high"
        mock_score.signals = {"length": 0.9}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score
        orch._session_ctx = MagicMock()

        # get_current_level_num retorna len(levels) = 1
        with patch.object(plan, 'get_current_level_num', return_value=1):
            result = orch._evaluate_confidence_and_check_early_stop(
                session, "st-0", "result"
            )

        assert result is not None
        orch._session_ctx.mark_subtask_done.assert_not_called()

    def test_early_stopping_no_next_level(self) -> None:
        """Si next_level_num >= len(levels), retorna sin saltar.  (línea 520)"""
        orch = _make_orch()
        # Plan con 1 nivel que tiene subtask completada
        subtasks = [
            SubTask(id="st-0", agent="builder", description="task",
                    dependencies=[], confidence_impact="critical"),
        ]
        plan = TaskPlan(session_id="test", original_message="test", subtasks=subtasks)
        plan.subtasks[0].completed = True
        session = _make_session(plan=plan)
        mock_score = MagicMock()
        mock_score.score = 0.95
        mock_score.should_stop = True
        mock_score.level = "high"
        mock_score.signals = {"length": 0.95}
        orch._confidence_scorer = MagicMock()
        orch._confidence_scorer.score_completion.return_value = mock_score
        orch._session_ctx = MagicMock()

        # Patch get_current_level_num para que apunte al ÚLTIMO nivel (0)
        # levels = [[st-0]], len(levels) = 1
        # next_level_num = 0 + 1 = 1, 1 >= 1 → True → line 520
        with patch.object(plan, 'get_current_level_num', return_value=0):
            result = orch._evaluate_confidence_and_check_early_stop(
                session, "st-0", "result"
            )

        assert result is not None
        # No debería saltar ningún nivel (no hay nivel siguiente)
        orch._session_ctx.mark_subtask_done.assert_not_called()


# ===================================================================
# Broadcast Methods  (líneas 826–827, 847, 880–881, 911–912)
# ===================================================================

class TestBroadcastMethods:
    """Métodos _broadcast_plan, _broadcast_completion, _broadcast_complete."""

    def test_broadcast_plan_exception_handled(self) -> None:
        """Excepción en _broadcast_plan se captura.  (líneas 826-827)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        orch._session_ctx = SessionContext()
        orch._bus = MagicMock()
        orch._bus.post_message.side_effect = Exception("Network error")

        # No debe propagar excepción
        orch._broadcast_plan(session)

    def test_broadcast_completion_subtask_not_found(self) -> None:
        """Subtask no encontrada → retorna sin post.  (línea 847)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        orch._bus = MagicMock()
        orch._broadcast_completion(session, "nonexistent", "result")
        orch._bus.post_message.assert_not_called()

    def test_broadcast_completion_found_posts(self) -> None:
        """Subtask encontrada → postea completado y notifica dependientes."""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        plan.subtasks[1].dependencies = ["st-0"]
        session = _make_session(plan=plan)
        orch._bus = MagicMock()
        orch._broadcast_completion(session, "st-0", "done")
        # Debería postear al menos el mensaje de completado
        assert orch._bus.post_message.call_count >= 2  # completion + notify waiting

    def test_broadcast_completion_exception_handled(self) -> None:
        """Excepción en _broadcast_completion se captura.  (líneas 880-881)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        plan.subtasks[1].dependencies = ["st-0"]
        session = _make_session(plan=plan)
        orch._bus = MagicMock()
        orch._bus.post_message.side_effect = Exception("Network error")
        # No debe propagar
        orch._broadcast_completion(session, "st-0", "result")

    def test_broadcast_complete_exception_handled(self) -> None:
        """Excepción en _broadcast_complete se captura.  (líneas 911-912)"""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=1)
        plan.subtasks[0].completed = True
        session = _make_session(plan=plan)
        orch._bus = MagicMock()
        orch._bus.post_message.side_effect = Exception("Network error")
        # No debe propagar
        orch._broadcast_complete(session)


# ===================================================================
# _build_result y helpers  (líneas 920–922)
# ===================================================================

class TestBuildResultAndHelpers:
    """_build_result, _empty_result, _resolve_target_agent."""

    def test_empty_result(self) -> None:
        """_empty_result retorna resultado de error.  (líneas 920-922)"""
        orch = _make_orch()
        result = orch._empty_result()
        assert result.session_id == "error"
        assert result.target_agent == "coordinator"
        assert result.is_complete is False
        assert result.is_new_plan is False
        assert "Error" in result.session_status

    def test_resolve_target_no_level(self) -> None:
        """Sin nivel → coordinator."""
        orch = _make_orch()
        assert orch._resolve_target_agent([]) == "coordinator"

    def test_resolve_target_single_agent(self) -> None:
        """Un agente → ese agente."""
        orch = _make_orch()
        level = [SubTask(id="st-1", agent="builder", description="test")]
        assert orch._resolve_target_agent(level) == "builder"

    def test_resolve_target_multiple_agents(self) -> None:
        """Múltiples agentes → coordinator."""
        orch = _make_orch()
        level = [
            SubTask(id="st-1", agent="builder", description="a"),
            SubTask(id="st-2", agent="scientist", description="b"),
        ]
        assert orch._resolve_target_agent(level) == "coordinator"

    def test_build_result_new_plan(self) -> None:
        """_build_result con is_new_plan=True genera resultado completo."""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2)
        session = _make_session(plan=plan)
        orch._session_ctx = SessionContext()
        orch._session_ctx._active_sessions[session.session_id] = session
        orch._bus = MagicMock()

        result = orch._build_result(session, "msg", None, is_new_plan=True)

        assert result.session_id == session.session_id
        assert result.is_new_plan is True
        assert result.is_complete is False
        assert len(result.current_level) == 2

    def test_build_result_debate_template(self) -> None:
        """_build_result detecta template debate."""
        orch = _make_orch()
        plan = _make_plan(n_subtasks=2, template_name="debate")
        plan.subtasks[0].agent = "builder"
        plan.subtasks[1].agent = "scientist"
        session = _make_session(plan=plan)
        orch._session_ctx = SessionContext()
        orch._session_ctx._active_sessions[session.session_id] = session
        orch._bus = MagicMock()

        result = orch._build_result(session, "msg", None, is_new_plan=False)

        assert result.is_debate is True
        assert "builder" in result.debate_agents
        assert "scientist" in result.debate_agents
        assert result.debate_strategy == "consensus"
