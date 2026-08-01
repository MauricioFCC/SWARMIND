"""Tests para MetaClaw — selector adaptativo de herramientas con meta-aprendizaje.

Cubre:
- Validacion de parametros del constructor
- Registro de herramientas
- Seleccion (Thompson Sampling, exploracion, sin herramientas)
- Registro de outcomes y actualizacion de posteriors
- Estadisticas de herramientas y tareas
- Reset de herramientas
- Historial de selecciones
- Concurrencia
"""
from __future__ import annotations

import threading

import pytest

from harness.orchestrator.metaclaw import (
    ALPHA_PRIOR,
    BETA_PRIOR,
    DEFAULT_WINDOW_SIZE,
    TASK_VECTOR_DIM,
    MetaClaw,
    SelectionRecord,
    ToolRecord,
)


# ---------------------------------------------------------------------------
# Validacion de parametros
# ---------------------------------------------------------------------------


class TestMetaClawInit:
    """Tests del constructor y validacion."""

    def test_init_defaults(self):
        """Inicializa con defaults razonables."""
        m = MetaClaw()
        assert m._alpha_prior == ALPHA_PRIOR
        assert m._beta_prior == BETA_PRIOR
        assert m._window_size == DEFAULT_WINDOW_SIZE
        assert m._task_vector_dim == TASK_VECTOR_DIM

    def test_init_starts_empty(self):
        """Estado inicial sin herramientas ni historial."""
        m = MetaClaw()
        assert m._tool_records == {}
        assert len(m._selection_history) == 0
        assert len(m._task_embeddings) == 0

    def test_init_invalid_alpha_raises(self):
        """alpha_prior <= 0 lanza ValueError."""
        with pytest.raises(ValueError, match="alpha_prior"):
            MetaClaw(alpha_prior=0)
        with pytest.raises(ValueError, match="alpha_prior"):
            MetaClaw(alpha_prior=-1.0)

    def test_init_invalid_beta_raises(self):
        """beta_prior <= 0 lanza ValueError."""
        with pytest.raises(ValueError, match="beta_prior"):
            MetaClaw(beta_prior=0)

    def test_init_window_too_small_raises(self):
        """window_size < 10 lanza ValueError."""
        with pytest.raises(ValueError, match="window_size"):
            MetaClaw(window_size=5)

    def test_init_task_vector_dim_too_small_raises(self):
        """task_vector_dim < 4 lanza ValueError."""
        with pytest.raises(ValueError, match="task_vector_dim"):
            MetaClaw(task_vector_dim=2)

    def test_init_invalid_learning_rate_raises(self):
        """learning_rate fuera de [0, 1] lanza ValueError."""
        with pytest.raises(ValueError, match="learning_rate"):
            MetaClaw(learning_rate=1.5)

    def test_init_invalid_exploration_rate_raises(self):
        """exploration_rate fuera de [0, 1] lanza ValueError."""
        with pytest.raises(ValueError, match="exploration_rate"):
            MetaClaw(exploration_rate=-0.1)


# ---------------------------------------------------------------------------
# Registro de herramientas
# ---------------------------------------------------------------------------


class TestMetaClawRegisterTool:
    """Tests de register_tool."""

    def test_register_single_tool(self):
        """Registra una herramienta nueva."""
        m = MetaClaw()
        m.register_tool("gpt-4")
        assert "gpt-4" in m._tool_records
        assert isinstance(m._tool_records["gpt-4"], ToolRecord)

    def test_register_duplicate_is_noop(self):
        """Registrar dos veces la misma herramienta no duplica (idempotente)."""
        m = MetaClaw()
        m.register_tool("tool")
        before = m._tool_records["tool"]
        m.register_tool("tool")
        after = m._tool_records["tool"]
        assert before is after

    def test_register_empty_name_raises(self):
        """tool_name vacio lanza ValueError."""
        m = MetaClaw()
        with pytest.raises(ValueError, match="tool_name"):
            m.register_tool("")

    def test_register_whitespace_name_raises(self):
        """tool_name solo espacios lanza ValueError."""
        m = MetaClaw()
        with pytest.raises(ValueError, match="tool_name"):
            m.register_tool("   ")

    def test_register_multiple_tools(self):
        """Registrar varias herramientas."""
        m = MetaClaw()
        for name in ["a", "b", "c"]:
            m.register_tool(name)
        assert len(m._tool_records) == 3


# ---------------------------------------------------------------------------
# Seleccion de herramientas
# ---------------------------------------------------------------------------


class TestMetaClawSelectTool:
    """Tests de select_tool."""

    def test_select_without_tools_raises(self):
        """select_tool sin herramientas registradas lanza RuntimeError."""
        m = MetaClaw()
        with pytest.raises(RuntimeError, match="herramientas registradas"):
            m.select_tool("code")

    def test_select_returns_registered_tool(self):
        """La herramienta devuelta esta en el registro."""
        m = MetaClaw(exploration_rate=0.0)
        m.register_tool("a")
        m.register_tool("b")
        m.register_tool("c")
        for _ in range(10):
            tool = m.select_tool("code")
            assert tool in {"a", "b", "c"}

    def test_select_uses_exploration(self):
        """Con exploration_rate=1.0, siempre elige aleatoriamente."""
        m = MetaClaw(exploration_rate=1.0)
        m.register_tool("only_one")
        # Incluso con 1 sola herramienta, la "exploracion" la elige
        tool = m.select_tool("code")
        assert tool == "only_one"

    def test_select_unknown_task_type_initializes(self):
        """task_type nuevo se inicializa y registra en known_task_types."""
        m = MetaClaw(exploration_rate=0.0)
        m.register_tool("a")
        m.select_tool("completely_new_type")
        assert "completely_new_type" in m._known_task_types
        assert m._known_task_types["completely_new_type"] == 1

    def test_select_increments_known_task_types(self):
        """Llamadas sucesivas al mismo task_type incrementan el contador."""
        m = MetaClaw(exploration_rate=0.0)
        m.register_tool("a")
        for _ in range(5):
            m.select_tool("frequent")
        assert m._known_task_types["frequent"] == 5

    def test_select_with_context_learns_embedding(self):
        """context no-vacio se usa para aprender el embedding de la tarea."""
        m = MetaClaw()
        m.register_tool("a")
        m.select_tool("code", context={"lang": "python", "complexity": 0.7})
        assert "code" in m._task_embeddings
        assert len(m._task_embeddings["code"]) == m._task_vector_dim

    def test_select_with_none_context_works(self):
        """context=None se trata como dict vacio sin error."""
        m = MetaClaw()
        m.register_tool("a")
        tool = m.select_tool("code", context=None)
        assert tool == "a"


# ---------------------------------------------------------------------------
# Registro de outcomes
# ---------------------------------------------------------------------------


class TestMetaClawRecordOutcome:
    """Tests de record_outcome."""

    def test_record_outcome_unknown_tool_raises(self):
        """tool_name no registrado lanza ValueError."""
        m = MetaClaw()
        with pytest.raises(ValueError, match="no esta registrada"):
            m.record_outcome("code", {}, "ghost", True, 1.0, 100.0)

    def test_record_outcome_negative_latency_raises(self):
        """latency < 0 lanza ValueError."""
        m = MetaClaw()
        m.register_tool("a")
        with pytest.raises(ValueError, match="latency"):
            m.record_outcome("code", {}, "a", True, -1.0, 100.0)

    def test_record_outcome_negative_cost_raises(self):
        """cost < 0 lanza ValueError."""
        m = MetaClaw()
        m.register_tool("a")
        with pytest.raises(ValueError, match="cost"):
            m.record_outcome("code", {}, "a", True, 1.0, -50.0)

    def test_record_outcome_invalid_confidence_raises(self):
        """confidence fuera de [0, 1] lanza ValueError."""
        m = MetaClaw()
        m.register_tool("a")
        with pytest.raises(ValueError, match="confidence"):
            m.record_outcome("code", {}, "a", True, 1.0, 100.0, confidence=1.5)
        with pytest.raises(ValueError, match="confidence"):
            m.record_outcome("code", {}, "a", True, 1.0, 100.0, confidence=-0.1)

    def test_record_outcome_success_updates_record(self):
        """Tras exito, total_calls y successes incrementan."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", True, 1.0, 100.0)
        rec = m._tool_records["a"]
        assert rec.total_calls == 1
        assert rec.successes == 1
        assert rec.failures == 0
        assert rec.total_latency == 1.0
        assert rec.total_cost == 100.0

    def test_record_outcome_failure_updates_record(self):
        """Tras fallo, failures incrementa y successes no."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", False, 2.0, 200.0)
        rec = m._tool_records["a"]
        assert rec.total_calls == 1
        assert rec.successes == 0
        assert rec.failures == 1

    def test_record_outcome_updates_posterior(self):
        """Tras outcome, el posterior (alpha, beta) cambia."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", True, 1.0, 50.0)
        # El posterior (alpha, beta) debe existir y alpha debe ser > prior
        alpha, beta = m._posteriors["code"]["a"]
        assert alpha > ALPHA_PRIOR  # subio por exito
        assert beta >= BETA_PRIOR

    def test_record_outcome_returns_selection_record(self):
        """record_outcome devuelve SelectionRecord con datos correctos."""
        m = MetaClaw()
        m.register_tool("a")
        result = m.record_outcome("code", {"lang": "py"}, "a", True, 1.5, 75.0, confidence=0.8)
        assert isinstance(result, SelectionRecord)
        # SelectionRecord usa 'selected_tool' (no 'tool_name')
        assert result.selected_tool == "a"
        assert result.task_type == "code"
        assert result.success is True
        assert result.latency == 1.5
        assert result.cost == 75.0
        assert result.confidence == 0.8


# ---------------------------------------------------------------------------
# Estadisticas y consultas
# ---------------------------------------------------------------------------


class TestMetaClawStats:
    """Tests de get_best_tool, get_tool_stats, get_task_performance, get_all_stats."""

    def test_get_best_tool_unknown_task_returns_registered(self):
        """get_best_tool devuelve una herramienta registrada (fallback uniforme)."""
        m = MetaClaw()
        m.register_tool("a")
        # Sin datos para 'never_seen', devuelve una herramienta registrada (no falla)
        best = m.get_best_tool("never_seen")
        assert best == "a"

    def test_get_best_tool_returns_registered(self):
        """Despues de outcomes, devuelve la herramienta con mejor posterior."""
        m = MetaClaw(exploration_rate=0.0)
        m.register_tool("good")
        m.register_tool("bad")
        # Entrenar: good siempre exitoso, bad siempre falla
        for _ in range(5):
            m.record_outcome("code", {}, "good", True, 1.0, 50.0)
            m.record_outcome("code", {}, "bad", False, 2.0, 200.0)
        best = m.get_best_tool("code")
        assert best == "good"

    def test_get_tool_stats_unknown_returns_none(self):
        """get_tool_stats de herramienta desconocida devuelve None."""
        m = MetaClaw()
        assert m.get_tool_stats("ghost") is None

    def test_get_tool_stats_existing(self):
        """get_tool_stats devuelve dict con campos esperados."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", True, 1.0, 50.0)
        m.record_outcome("code", {}, "a", False, 2.0, 100.0)
        stats = m.get_tool_stats("a")
        assert stats is not None
        assert stats["tool_name"] == "a"
        assert stats["total_calls"] == 2
        assert stats["successes"] == 1
        assert stats["failures"] == 1
        assert stats["success_rate"] == 0.5
        assert "avg_latency" in stats
        assert "avg_cost" in stats
        assert "task_types" in stats

    def test_get_task_performance_empty(self):
        """Sin outcomes, get_task_performance devuelve None."""
        m = MetaClaw()
        assert m.get_task_performance("unknown") is None

    def test_get_task_performance_returns_dict(self):
        """Tras outcomes, devuelve dict agregado con tools_used y best_tool."""
        m = MetaClaw()
        m.register_tool("a")
        m.register_tool("b")
        m.record_outcome("code", {}, "a", True, 1.0, 50.0)
        m.record_outcome("code", {}, "b", False, 2.0, 200.0)
        perf = m.get_task_performance("code")
        assert perf is not None
        assert "task_type" in perf
        assert "tools_used" in perf
        assert "best_tool" in perf
        assert "total_calls" in perf
        assert set(perf["tools_used"].keys()) == {"a", "b"}
        assert perf["best_tool"] == "a"  # good con exito vs bad con fallo

    def test_get_all_stats_structure(self):
        """get_all_stats devuelve dict con secciones esperadas."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", True, 1.0, 50.0)
        stats = m.get_all_stats()
        assert "tools" in stats
        assert "task_types" in stats
        assert "total_selections" in stats
        assert stats["registered_tools"] == 1
        assert stats["total_selections"] == 1
        assert "a" in stats["tools"]


# ---------------------------------------------------------------------------
# Reset y misc
# ---------------------------------------------------------------------------


class TestMetaClawReset:
    """Tests de reset_tool."""

    def test_reset_existing_tool_returns_true(self):
        """reset_tool de herramienta existente devuelve True."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", True, 1.0, 50.0)
        assert m.reset_tool("a") is True
        rec = m._tool_records["a"]
        assert rec.total_calls == 0
        assert rec.successes == 0
        assert rec.failures == 0

    def test_reset_unknown_tool_returns_false(self):
        """reset_tool de herramienta desconocida devuelve False."""
        m = MetaClaw()
        assert m.reset_tool("ghost") is False

    def test_get_selection_history_empty(self):
        """Sin selecciones, historial vacio."""
        m = MetaClaw()
        assert m.get_selection_history() == []

    def test_get_selection_history_filled(self):
        """Tras outcomes, historial contiene dicts con campos esperados."""
        m = MetaClaw()
        m.register_tool("a")
        m.record_outcome("code", {}, "a", True, 1.0, 50.0)
        m.record_outcome("test", {}, "a", False, 2.0, 100.0)
        hist = m.get_selection_history()
        assert len(hist) == 2
        # get_selection_history devuelve list[dict], no list[SelectionRecord]
        assert all(isinstance(r, dict) for r in hist)
        assert all("selected_tool" in r for r in hist)
        assert all("task_type" in r for r in hist)


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------


class TestMetaClawThreadSafety:
    """Verifica que MetaClaw es seguro bajo concurrencia."""

    def test_concurrent_register_tools(self):
        """Multiples hilos registrando herramientas sin corrupcion."""
        m = MetaClaw()
        threads = []
        for i in range(20):
            t = threading.Thread(target=m.register_tool, args=(f"tool_{i}",))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert len(m._tool_records) == 20

    def test_concurrent_record_outcomes(self):
        """Multiples hilos registrando outcomes sin race conditions."""
        m = MetaClaw()
        m.register_tool("a")
        m.register_tool("b")
        threads = []
        for i in range(30):
            t = threading.Thread(
                target=m.record_outcome,
                args=("code", {}, "a" if i % 2 == 0 else "b", True, 1.0, 50.0),
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        total = m._tool_records["a"].total_calls + m._tool_records["b"].total_calls
        assert total == 30


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestMetaClawDataClasses:
    """Tests de ToolRecord y SelectionRecord."""

    def test_tool_record_defaults(self):
        """ToolRecord con defaults razonables."""
        rec = ToolRecord(tool_name="x")
        assert rec.total_calls == 0
        assert rec.successes == 0
        assert rec.failures == 0
        assert rec.total_latency == 0.0
        assert rec.total_cost == 0.0
        assert rec.last_used == 0.0
        assert rec.task_types == {}

    def test_selection_record_required_fields(self):
        """SelectionRecord con campos requeridos (usa selected_tool)."""
        sr = SelectionRecord(
            task_type="code", context={}, selected_tool="a",
            success=True, latency=1.0, cost=50.0,
        )
        assert sr.selected_tool == "a"
        assert sr.task_type == "code"
        assert sr.success is True
        assert sr.confidence == 0.0  # default
        assert sr.reward == 0.0  # default
        assert sr.timestamp > 0
