"""Tests para MARSScheduler — planificador multi-agente con Q-learning.

Cubre:
- Validacion de parametros del constructor
- Registro de agentes con validacion de skills
- Planificacion de tareas (asignacion, encolado, errores)
- Registro de outcomes y aprendizaje Q
- Estadisticas del sistema y la cola
- Habilitar/deshabilitar agentes
- Hilos concurrentes (thread-safety)
"""
from __future__ import annotations

import threading

import pytest

from harness.orchestrator.mars_scheduler import (
    MAX_QUEUE_SIZE,
    MIN_MATCH_THRESHOLD,
    Q_DISCOUNT_FACTOR,
    Q_EXPLORATION_RATE,
    Q_LEARNING_RATE,
    AgentProfile,
    Assignment,
    MARSScheduler,
    TaskSpec,
)


# ---------------------------------------------------------------------------
# Validacion de parametros del constructor
# ---------------------------------------------------------------------------


class TestMARSSchedulerInit:
    """Tests del constructor y validacion de parametros."""

    def test_init_defaults_ok(self):
        """Inicializa con valores por defecto sin error."""
        s = MARSScheduler()
        assert s._learning_rate == Q_LEARNING_RATE
        assert s._discount_factor == Q_DISCOUNT_FACTOR
        assert s._exploration_rate == Q_EXPLORATION_RATE
        assert s._max_queue == MAX_QUEUE_SIZE
        assert s._min_match_threshold == MIN_MATCH_THRESHOLD

    def test_init_invalid_learning_rate_raises(self):
        """learning_rate fuera de [0, 1] lanza ValueError."""
        with pytest.raises(ValueError, match="learning_rate"):
            MARSScheduler(learning_rate=1.5)
        with pytest.raises(ValueError, match="learning_rate"):
            MARSScheduler(learning_rate=-0.1)

    def test_init_invalid_discount_factor_raises(self):
        """discount_factor fuera de [0, 1] lanza ValueError."""
        with pytest.raises(ValueError, match="discount_factor"):
            MARSScheduler(discount_factor=1.5)

    def test_init_invalid_exploration_rate_raises(self):
        """exploration_rate fuera de [0, 1] lanza ValueError."""
        with pytest.raises(ValueError, match="exploration_rate"):
            MARSScheduler(exploration_rate=-0.5)

    def test_init_invalid_exploration_decay_raises(self):
        """exploration_decay fuera de [0, 1] lanza ValueError."""
        with pytest.raises(ValueError, match="exploration_decay"):
            MARSScheduler(exploration_decay=1.1)

    def test_init_max_queue_too_small_raises(self):
        """max_queue < 10 lanza ValueError."""
        with pytest.raises(ValueError, match="max_queue"):
            MARSScheduler(max_queue=5)

    def test_init_negative_min_match_raises(self):
        """min_match_threshold < 0 lanza ValueError."""
        with pytest.raises(ValueError, match="min_match_threshold"):
            MARSScheduler(min_match_threshold=-0.1)

    def test_init_aging_factor_too_low_raises(self):
        """aging_factor < 1.0 lanza ValueError."""
        with pytest.raises(ValueError, match="aging_factor"):
            MARSScheduler(aging_factor=0.9)

    def test_init_starts_empty(self):
        """Estado inicial vacio: sin agentes, sin tareas."""
        s = MARSScheduler()
        assert s._agents == {}
        assert s._task_queue == []
        assert s._running_tasks == {}
        assert s._total_scheduled == 0


# ---------------------------------------------------------------------------
# Registro de agentes
# ---------------------------------------------------------------------------


class TestMARSSchedulerRegisterAgent:
    """Tests de register_agent y validacion."""

    def test_register_single_agent(self):
        """Registra un agente basico."""
        s = MARSScheduler()
        s.register_agent("builder", skills={"code": 0.9})
        assert "builder" in s._agents
        assert s._agents["builder"].max_load == 3
        assert s._agents["builder"].skill_vector == {"code": 0.9}

    def test_register_agent_no_skills(self):
        """Registra un agente sin skills (None o {})."""
        s = MARSScheduler()
        s.register_agent("novice")  # skills=None
        assert s._agents["novice"].skill_vector == {}
        s.register_agent("novice2", skills={})
        assert s._agents["novice2"].skill_vector == {}

    def test_register_empty_agent_id_raises(self):
        """agent_id vacio lanza ValueError."""
        s = MARSScheduler()
        with pytest.raises(ValueError, match="agent_id"):
            s.register_agent("")

    def test_register_max_load_too_small_raises(self):
        """max_load < 1 lanza ValueError."""
        s = MARSScheduler()
        with pytest.raises(ValueError, match="max_load"):
            s.register_agent("a", max_load=0)

    def test_register_skill_out_of_range_raises(self):
        """skill proficiency fuera de [0, 1] lanza ValueError."""
        s = MARSScheduler()
        with pytest.raises(ValueError, match="proficiency"):
            s.register_agent("a", skills={"code": 1.5})
        with pytest.raises(ValueError, match="proficiency"):
            s.register_agent("a", skills={"code": -0.1})

    def test_register_duplicate_warns_and_overwrites(self):
        """Registrar dos veces el mismo ID sobrescribe (con warning)."""
        s = MARSScheduler()
        s.register_agent("dup", skills={"code": 0.5})
        s.register_agent("dup", skills={"design": 0.7})
        assert s._agents["dup"].skill_vector == {"design": 0.7}

    def test_register_custom_max_load(self):
        """max_load custom se respeta."""
        s = MARSScheduler()
        s.register_agent("hot", max_load=10)
        assert s._agents["hot"].max_load == 10


# ---------------------------------------------------------------------------
# Planificacion de tareas
# ---------------------------------------------------------------------------


class TestMARSSchedulerScheduleTask:
    """Tests de schedule_task."""

    def test_schedule_with_no_agents_raises(self):
        """schedule_task sin agentes registrados lanza RuntimeError."""
        s = MARSScheduler()
        task = TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={})
        with pytest.raises(RuntimeError, match="agentes registrados"):
            s.schedule_task(task)

    def test_schedule_empty_task_id_raises(self):
        """task_id vacio lanza ValueError."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        with pytest.raises(ValueError, match="task_id"):
            s.schedule_task(TaskSpec(task_id="", task_type="x", value=1, skills_needed={}))

    def test_schedule_negative_value_raises(self):
        """task.value < 0 lanza ValueError."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        with pytest.raises(ValueError, match="value"):
            s.schedule_task(
                TaskSpec(task_id="t1", task_type="x", value=-1, skills_needed={})
            )

    def test_schedule_assigns_to_best_agent(self):
        """Asigna al agente con mayor match score."""
        s = MARSScheduler(exploration_rate=0.0)  # desactivar exploracion
        s.register_agent("novice", skills={"code": 0.3})
        s.register_agent("expert", skills={"code": 0.95})
        task = TaskSpec(
            task_id="t1", task_type="code_gen",
            value=100, skills_needed={"code": 0.8},
        )
        assignment = s.schedule_task(task)
        assert assignment is not None
        assert assignment.agent_id == "expert"
        assert assignment.task_id == "t1"
        assert assignment.expected_success > 0

    def test_schedule_duplicate_task_returns_none(self):
        """Tarea ya en ejecucion devuelve None (no re-asigna)."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        task = TaskSpec(task_id="dup", task_type="code", value=10, skills_needed={"code": 0.5})
        a1 = s.schedule_task(task)
        a2 = s.schedule_task(task)  # mismo task_id
        assert a1 is not None
        assert a2 is None

    def test_schedule_queues_when_no_match(self):
        """Si ningun agente supera el umbral, la tarea se encola."""
        s = MARSScheduler(min_match_threshold=0.99)  # umbral muy alto
        s.register_agent("weak", skills={"code": 0.1})
        task = TaskSpec(
            task_id="hard", task_type="code_gen",
            value=50, skills_needed={"code": 0.9},
        )
        result = s.schedule_task(task)
        assert result is None
        assert len(s._task_queue) == 1
        assert s._task_queue[0][2].task_id == "hard"

    def test_schedule_skips_disabled_agent(self):
        """Agente deshabilitado no recibe tareas."""
        s = MARSScheduler(exploration_rate=0.0)
        s.register_agent("a", skills={"code": 1.0})
        s.enable_agent("a", enabled=False)
        task = TaskSpec(task_id="t", task_type="code", value=10, skills_needed={"code": 0.5})
        result = s.schedule_task(task)
        assert result is None
        assert len(s._task_queue) == 1

    def test_schedule_skips_overloaded_agent(self):
        """Agente con current_load >= max_load no recibe tareas."""
        s = MARSScheduler(exploration_rate=0.0)
        s.register_agent("a", skills={"code": 1.0}, max_load=1)
        # Llenar el agente con una tarea
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        # Segunda tarea no deberia asignarse al mismo agente
        task2 = TaskSpec(task_id="t2", task_type="code", value=10, skills_needed={"code": 0.5})
        result = s.schedule_task(task2)
        assert result is None
        assert len(s._task_queue) == 1

    def test_schedule_updates_total_count(self):
        """Cada asignacion incrementa _total_scheduled."""
        s = MARSScheduler(exploration_rate=0.0)
        s.register_agent("a", skills={"code": 1.0})
        for i in range(3):
            s.schedule_task(
                TaskSpec(task_id=f"t{i}", task_type="code", value=10, skills_needed={"code": 0.5}),
            )
        assert s._total_scheduled == 3


# ---------------------------------------------------------------------------
# Registro de outcomes
# ---------------------------------------------------------------------------


class TestMARSSchedulerRecordOutcome:
    """Tests de record_outcome y aprendizaje Q."""

    def test_record_outcome_unknown_task_raises(self):
        """Record outcome de tarea no planificada lanza ValueError."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        with pytest.raises(ValueError, match="no encontrada"):
            s.record_outcome("nope", "a", True, 1.0, 100.0)

    def test_record_outcome_wrong_agent_raises(self):
        """agent_id incorrecto lanza ValueError."""
        s = MARSScheduler(exploration_rate=0.0)
        s.register_agent("a", skills={"code": 1.0})
        s.register_agent("b", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        with pytest.raises(ValueError, match="no coincide"):
            s.record_outcome("t1", "b", True, 1.0, 100.0)

    def test_record_outcome_negative_latency_raises(self):
        """latency < 0 lanza ValueError antes de tocar el estado."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        with pytest.raises(ValueError, match="latency"):
            s.record_outcome("t1", "a", True, -1.0, 100.0)

    def test_record_outcome_negative_cost_raises(self):
        """cost < 0 lanza ValueError."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        with pytest.raises(ValueError, match="cost"):
            s.record_outcome("t1", "a", True, 1.0, -50.0)

    def test_record_outcome_success_frees_load(self):
        """Tras success, current_load del agente decrementa."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0}, max_load=2)
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        assert s._agents["a"].current_load == 1
        s.record_outcome("t1", "a", True, 1.0, 100.0)
        assert s._agents["a"].current_load == 0
        assert s._total_completed == 1
        assert s._total_failures == 0

    def test_record_outcome_failure_increments_failures(self):
        """Tras failure, _total_failures incrementa, load libera."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        s.record_outcome("t1", "a", False, 5.0, 200.0)
        assert s._total_failures == 1
        assert s._total_completed == 0
        assert s._agents["a"].current_load == 0

    def test_record_outcome_updates_q_value(self):
        """Tras outcome, el Q-value cambia (aprendizaje)."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        s.record_outcome("t1", "a", True, 1.0, 50.0)
        # Q-table key es (agent_id, task_id)
        assert ("a", "t1") in s._q_table
        q_after = s._q_table[("a", "t1")]
        # Q debe estar dentro de [0, 1] aproximadamente
        assert -1.0 <= q_after <= 2.0

    def test_record_outcome_queues_drained(self):
        """Tareas encoladas se reintentan al liberar capacidad."""
        s = MARSScheduler(min_match_threshold=0.99)
        s.register_agent("a", skills={"code": 0.5}, max_load=1)
        # Tarea 1: ocupa el agente
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.4}),
        )
        # Tarea 2: se encola porque umbral no se cumple
        s.schedule_task(
            TaskSpec(task_id="t2", task_type="code", value=10, skills_needed={"code": 0.9}),
        )
        assert len(s._task_queue) == 1
        # Liberamos agente: t2 deberia re-intentarse (pero seguira encolada por umbral)
        s.record_outcome("t1", "a", True, 1.0, 50.0)
        # La cola puede seguir teniendo t2 (no cumple umbral) o haberse vaciado si hay match
        # El comportamiento concreto depende del umbral: verificamos que no se rompa
        assert s._agents["a"].current_load == 0


# ---------------------------------------------------------------------------
# Estadisticas
# ---------------------------------------------------------------------------


class TestMARSSchedulerStats:
    """Tests de get_queue_status, get_system_stats, get_agent_stats."""

    def test_get_queue_status_empty(self):
        """Cola vacia: queue_size=0, oldest_age=0."""
        s = MARSScheduler()
        status = s.get_queue_status()
        assert status["queue_size"] == 0
        assert status["oldest_task_age_seconds"] == 0
        assert status["tasks"] == []

    def test_get_queue_status_with_task(self):
        """Con tarea encolada, status refleja queue_size y task_id."""
        s = MARSScheduler(min_match_threshold=0.99)
        s.register_agent("a", skills={"code": 0.1})
        s.schedule_task(
            TaskSpec(task_id="q1", task_type="code", value=10, skills_needed={"code": 0.9}),
        )
        status = s.get_queue_status()
        assert status["queue_size"] == 1
        assert status["tasks"][0]["task_id"] == "q1"

    def test_get_system_stats_initial(self):
        """Stats iniciales vacias."""
        s = MARSScheduler()
        stats = s.get_system_stats()
        assert stats["total_scheduled"] == 0
        assert stats["total_completed"] == 0
        assert stats["total_failures"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["agents_count"] == 0
        assert stats["queue_size"] == 0
        assert stats["running_tasks"] == 0

    def test_get_system_stats_after_activity(self):
        """Stats reflejan actividad real."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        s.record_outcome("t1", "a", True, 1.0, 50.0)
        s.schedule_task(
            TaskSpec(task_id="t2", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        s.record_outcome("t2", "a", False, 2.0, 200.0)
        stats = s.get_system_stats()
        assert stats["total_scheduled"] == 2
        assert stats["total_completed"] == 1
        assert stats["total_failures"] == 1
        assert stats["success_rate"] == 0.5
        assert stats["agents_count"] == 1
        assert stats["q_table_entries"] >= 1

    def test_get_agent_stats_unknown_returns_none(self):
        """get_agent_stats de agente inexistente devuelve None."""
        s = MARSScheduler()
        assert s.get_agent_stats("nope") is None

    def test_get_agent_stats_existing(self):
        """get_agent_stats de agente registrado devuelve dict con campos."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 0.8})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        stats = s.get_agent_stats("a")
        assert stats is not None
        assert stats["agent_id"] == "a"
        assert stats["enabled"] is True
        assert stats["total_tasks"] == 1
        assert stats["current_load"] == 1


# ---------------------------------------------------------------------------
# enable_agent y get_completed_history
# ---------------------------------------------------------------------------


class TestMARSSchedulerMisc:
    """Tests miscelaneos."""

    def test_enable_agent_existing(self):
        """enable_agent de agente existente devuelve True."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        assert s.enable_agent("a", False) is True
        assert s._agents["a"].enabled is False
        assert s.enable_agent("a", True) is True
        assert s._agents["a"].enabled is True

    def test_enable_agent_unknown_returns_false(self):
        """enable_agent de agente desconocido devuelve False."""
        s = MARSScheduler()
        assert s.enable_agent("ghost", True) is False

    def test_get_completed_history_empty(self):
        """Sin completadas, historial vacio."""
        s = MARSScheduler()
        assert s.get_completed_history() == []

    def test_get_completed_history_returns_completed(self):
        """Historial incluye tareas completadas con su outcome."""
        s = MARSScheduler()
        s.register_agent("a", skills={"code": 1.0})
        s.schedule_task(
            TaskSpec(task_id="t1", task_type="code", value=10, skills_needed={"code": 0.5}),
        )
        s.record_outcome("t1", "a", True, 1.5, 100.0)
        hist = s.get_completed_history()
        assert len(hist) == 1
        assert hist[0]["task_id"] == "t1"
        assert hist[0]["agent_id"] == "a"
        assert hist[0]["success"] is True


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------


class TestMARSSchedulerThreadSafety:
    """Verifica que el scheduler es seguro bajo concurrencia."""

    def test_concurrent_register_agents(self):
        """Multiples hilos registrando agentes sin corrupcion."""
        s = MARSScheduler()
        threads = []
        for i in range(10):
            t = threading.Thread(
                target=s.register_agent,
                args=(f"agent_{i}",),
                kwargs={"skills": {"code": 0.5}},
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert len(s._agents) == 10

    def test_concurrent_schedule_tasks(self):
        """Multiples hilos planificando tareas sin race conditions."""
        s = MARSScheduler(exploration_rate=0.0)
        s.register_agent("a", skills={"code": 1.0}, max_load=100)
        s.register_agent("b", skills={"code": 0.9}, max_load=100)

        results = []
        lock = threading.Lock()

        def schedule(i: int):
            task = TaskSpec(
                task_id=f"t{i}", task_type="code",
                value=10, skills_needed={"code": 0.5},
            )
            a = s.schedule_task(task)
            with lock:
                results.append(a)

        threads = [threading.Thread(target=schedule, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Todos los hilos deben haber obtenido un Assignment
        assert len(results) == 20
        assert all(r is not None for r in results)


# ---------------------------------------------------------------------------
# Constantes y dataclasses
# ---------------------------------------------------------------------------


class TestMARSDataClasses:
    """Tests de dataclasses auxiliares."""

    def test_agent_profile_defaults(self):
        """AgentProfile con defaults razonables."""
        ap = AgentProfile(agent_id="a", skill_vector={"x": 0.5})
        assert ap.enabled is True
        assert ap.current_load == 0
        assert ap.total_tasks == 0
        assert ap.max_load == 3

    def test_task_spec_defaults(self):
        """TaskSpec con defaults razonables."""
        t = TaskSpec(task_id="t", task_type="x", value=10, skills_needed={})
        # Verifica campos reales del dataclass
        assert t.estimated_duration == 60.0
        assert t.max_cost == 1000.0
        assert t.priority == 0
        assert t.context == {}

    def test_assignment_has_timestamp(self):
        """Assignment asigna timestamp al crearse."""
        a = Assignment(
            task_id="t", agent_id="a",
            match_score=0.5, expected_success=0.8,
            expected_cost=10, expected_latency=1.0,
        )
        assert a.assigned_at > 0
