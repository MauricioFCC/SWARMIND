"""
Tests para TelemetryTracker — telemetría estructurada multi-agente.

Cubre: SubtaskRecord, LevelRecord, SessionTelemetry, TelemetryTracker,
       track_subtask decorator, export/load/clear.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from harness.orchestrator.telemetry import (
    LevelRecord,
    SessionTelemetry,
    SubtaskRecord,
    TelemetryTracker,
    track_subtask,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def subtask_record() -> SubtaskRecord:
    """SubtaskRecord de ejemplo."""
    return SubtaskRecord(
        subtask_id="st-1",
        agent="solver",
        description="Resolver tarea",
        status="success",
        start_time=1000.0,
        end_time=1005.0,
        duration_ms=5000.0,
    )


@pytest.fixture
def level_record(subtask_record: SubtaskRecord) -> LevelRecord:
    """LevelRecord con una subtask."""
    level = LevelRecord(level=1, start_time=1000.0, end_time=1010.0, status="success")
    level.subtasks.append(subtask_record)
    return level


@pytest.fixture
def session() -> SessionTelemetry:
    """SessionTelemetry de ejemplo con 2 niveles."""
    s = SessionTelemetry(
        session_id="sess-1",
        task="deploy",
        project="acme",
        start_time=1000.0,
        end_time=0.0,  # running
        status="running",
    )

    # Nivel 0
    l0 = LevelRecord(level=0, start_time=1000.0, end_time=1004.0, status="success")
    l0.subtasks.append(
        SubtaskRecord("st-a", "planner", "plan", "success", start_time=1000.0, end_time=1004.0)
    )
    l0.subtasks.append(
        SubtaskRecord("st-b", "planner", "plan2", "failed", start_time=1000.0, end_time=1003.0)
    )
    s.add_level(l0)

    # Nivel 1 (running)
    l1 = LevelRecord(level=1, start_time=1004.0, end_time=0.0, status="running")
    l1.subtasks.append(
        SubtaskRecord("st-c", "coder", "code", "success", start_time=1004.0, end_time=1008.0)
    )
    s.add_level(l1)

    s.total_subtasks = 3
    s.total_errors = 1
    s.total_warnings = 0
    s.agent_stats = {
        "planner": {"ok": 1, "error": 1, "total": 2},
        "coder": {"ok": 1, "error": 0, "total": 1},
    }
    return s


@pytest.fixture
def tracker(tmp_path: Path) -> TelemetryTracker:
    """TelemetryTracker con directorio temporal."""
    return TelemetryTracker(export_dir=str(tmp_path))


# ===========================================================================
# SubtaskRecord
# ===========================================================================


class TestSubtaskRecord:
    """Tests para SubtaskRecord — registro individual de subtask."""

    def test_elapsed_with_end_time(self) -> None:
        """elapsed: end_time > 0 → (end - start) * 1000."""
        r = SubtaskRecord("id", "a", "d", start_time=10.0, end_time=12.0)
        assert r.elapsed == 2000.0  # (12-10)*1000

    def test_elapsed_without_end_time(self) -> None:
        """elapsed: end_time == 0, start_time > 0 → (now - start) * 1000."""
        r = SubtaskRecord("id", "a", "d", start_time=10.0, end_time=0.0)
        now = time.time()
        assert r.elapsed == pytest.approx((now - 10.0) * 1000, rel=0.1)

    def test_elapsed_no_times(self) -> None:
        """elapsed: end_time == 0, start_time == 0 → 0.0."""
        r = SubtaskRecord("id", "a", "d", start_time=0.0, end_time=0.0)
        assert r.elapsed == 0.0

    def test_to_dict(self, subtask_record: SubtaskRecord) -> None:
        """to_dict: retorna dict con todos los campos."""
        d = subtask_record.to_dict()
        assert d["subtask_id"] == "st-1"
        assert d["agent"] == "solver"
        assert d["status"] == "success"
        assert d["duration_ms"] == 5000.0


# ===========================================================================
# LevelRecord
# ===========================================================================


class TestLevelRecord:
    """Tests para LevelRecord — nivel de ejecución."""

    def test_duration_ms_with_end_time(self) -> None:
        """duration_ms: end_time > 0 → (end - start) * 1000."""
        l = LevelRecord(level=1, start_time=10.0, end_time=15.0)
        assert l.duration_ms == 5000.0

    def test_duration_ms_without_end_time(self) -> None:
        """duration_ms: end_time == 0, start_time > 0 → (now - start) * 1000."""
        l = LevelRecord(level=1, start_time=10.0, end_time=0.0)
        now = time.time()
        assert l.duration_ms == pytest.approx((now - 10.0) * 1000, rel=0.1)

    def test_duration_ms_no_times(self) -> None:
        """duration_ms: end_time == 0, start_time == 0 → 0.0."""
        l = LevelRecord(level=1, start_time=0.0, end_time=0.0)
        assert l.duration_ms == 0.0

    def test_success_rate_empty(self) -> None:
        """success_rate: sin subtasks → 0.0."""
        l = LevelRecord(level=1)
        assert l.success_rate == 0.0

    def test_success_rate_all_success(self) -> None:
        """success_rate: todas success → 1.0."""
        l = LevelRecord(level=1)
        l.subtasks = [
            SubtaskRecord("a", "ag", "d", status="success"),
            SubtaskRecord("b", "ag", "d", status="success"),
        ]
        assert l.success_rate == 1.0

    def test_success_rate_mixed(self) -> None:
        """success_rate: mezcla success/failed."""
        l = LevelRecord(level=1)
        l.subtasks = [
            SubtaskRecord("a", "ag", "d", status="success"),
            SubtaskRecord("b", "ag", "d", status="failed"),
            SubtaskRecord("c", "ag", "d", status="success"),
        ]
        assert l.success_rate == pytest.approx(2 / 3)

    def test_to_dict(self, level_record: LevelRecord) -> None:
        """to_dict: incluye level, duracion, subtasks, success_rate."""
        d = level_record.to_dict()
        assert d["level"] == 1
        assert d["duration_ms"] == 10000.0
        assert d["subtask_count"] == 1
        assert d["success_rate"] == 1.0
        assert len(d["subtasks"]) == 1


# ===========================================================================
# SessionTelemetry
# ===========================================================================


class TestSessionTelemetry:
    """Tests para SessionTelemetry — sesión completa de telemetría."""

    def test_total_duration_ms_with_end_time(self) -> None:
        """total_duration_ms: end_time > 0 → (end - start) * 1000."""
        s = SessionTelemetry("sid", "task", start_time=10.0, end_time=20.0)
        assert s.total_duration_ms == 10000.0

    def test_total_duration_ms_without_end_time(self) -> None:
        """total_duration_ms: end_time == 0 → (now - start) * 1000."""
        s = SessionTelemetry("sid", "task", start_time=10.0, end_time=0.0)
        now = time.time()
        assert s.total_duration_ms == pytest.approx((now - 10.0) * 1000, rel=0.1)

    def test_success_rate_zero_subtasks(self) -> None:
        """success_rate: total_subtasks == 0 → 0.0."""
        s = SessionTelemetry("sid", "task")
        assert s.success_rate == 0.0

    def test_success_rate_all_success(self) -> None:
        """success_rate: todos success."""
        s = SessionTelemetry("sid", "task")
        l0 = LevelRecord(level=0)
        l0.subtasks.append(SubtaskRecord("a", "ag", "d", status="success"))
        s.add_level(l0)
        s.total_subtasks = 1
        assert s.success_rate == 1.0

    def test_success_rate_mixed(self) -> None:
        """success_rate: mezcla de estados."""
        s = SessionTelemetry("sid", "task")
        l0 = LevelRecord(level=0)
        l0.subtasks.append(SubtaskRecord("a", "ag", "d", status="success"))
        l0.subtasks.append(SubtaskRecord("b", "ag", "d", status="failed"))
        s.add_level(l0)
        s.total_subtasks = 2
        assert s.success_rate == 0.5

    def test_add_level(self) -> None:
        """add_level: agrega nivel a la lista."""
        s = SessionTelemetry("sid", "task")
        l = LevelRecord(level=0)
        s.add_level(l)
        assert len(s.levels) == 1
        assert s.levels[0] is l

    def test_record_subtask_new_level(self) -> None:
        """record_subtask: crea niveles intermedios si no existen."""
        s = SessionTelemetry("sid", "task")
        r = SubtaskRecord("st-1", "agent", "desc", status="success")
        s.record_subtask(2, r)
        assert len(s.levels) == 3  # levels[0], [1], [2]
        assert s.levels[2].subtasks[0] is r

    def test_record_subtask_increments_counters(self) -> None:
        """record_subtask: incrementa total_subtasks, errores, warnings."""
        s = SessionTelemetry("sid", "task")

        r1 = SubtaskRecord("st-1", "agent", "desc", status="success")
        s.record_subtask(0, r1)
        assert s.total_subtasks == 1
        assert s.total_errors == 0
        assert s.total_warnings == 0

        r2 = SubtaskRecord("st-2", "agent", "desc", status="failed", error="err")
        s.record_subtask(0, r2)
        assert s.total_subtasks == 2
        assert s.total_errors == 1

        r3 = SubtaskRecord("st-3", "agent", "desc", status="success", warning="warn")
        s.record_subtask(0, r3)
        assert s.total_subtasks == 3
        assert s.total_warnings == 1

    def test_record_subtask_updates_agent_stats(self) -> None:
        """record_subtask: actualiza estadísticas por agente."""
        s = SessionTelemetry("sid", "task")

        ok = SubtaskRecord("a", "planner", "d", status="success")
        fail = SubtaskRecord("b", "planner", "d", status="failed", error="e")
        s.record_subtask(0, ok)
        s.record_subtask(0, fail)

        assert s.agent_stats["planner"]["ok"] == 1
        assert s.agent_stats["planner"]["error"] == 1
        assert s.agent_stats["planner"]["total"] == 2

    def test_get_subtask_history(self, session: SessionTelemetry) -> None:
        """get_subtask_history: lista plana de todas las subtasks."""
        history = session.get_subtask_history()
        assert len(history) == 3
        assert history[0]["subtask_id"] == "st-a"
        assert history[1]["subtask_id"] == "st-b"
        assert history[2]["subtask_id"] == "st-c"
        # todos tienen los keys esperados
        for entry in history:
            assert "subtask_id" in entry
            assert "agent" in entry
            assert "description" in entry
            assert "timestamp" in entry

    def test_get_subtask_history_empty(self) -> None:
        """get_subtask_history: sin niveles ni subtasks → lista vacía."""
        s = SessionTelemetry("sid", "task")
        assert s.get_subtask_history() == []

    def test_record_error(self) -> None:
        """record_error: incrementa contador de errores."""
        s = SessionTelemetry("sid", "task")
        assert s.get_error_count() == 0
        s.record_error()
        assert s.get_error_count() == 1

    def test_record_warning(self) -> None:
        """record_warning: incrementa contador de warnings."""
        s = SessionTelemetry("sid", "task")
        assert s.get_warning_count() == 0
        s.record_warning()
        assert s.get_warning_count() == 1

    def test_finalize(self) -> None:
        """finalize: fija end_time, status, y niveles running."""
        s = SessionTelemetry("sid", "task", start_time=1000.0)
        s.add_level(LevelRecord(level=0, status="success"))
        s.add_level(LevelRecord(level=1, status="running"))

        before = time.time()
        s.finalize(status="completed")
        after = time.time()

        assert s.status == "completed"
        assert before <= s.end_time <= after
        # El nivel running se finalizó
        assert s.levels[1].status == "completed"
        assert before <= s.levels[1].end_time <= after

    def test_summary(self, session: SessionTelemetry) -> None:
        """summary: resumen ejecutivo con campos clave."""
        summ = session.summary()
        assert summ["session_id"] == "sess-1"
        assert summ["task"] == "deploy"
        assert summ["project"] == "acme"
        assert summ["status"] == "running"
        assert summ["levels"] == 2
        assert summ["total_subtasks"] == 3
        assert summ["total_errors"] == 1
        assert "total_duration_ms" in summ
        assert "success_rate" in summ
        assert "agent_stats" in summ

    def test_to_dict(self, session: SessionTelemetry) -> None:
        """to_dict: dump completo de la sesión."""
        d = session.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["total_subtasks"] == 3
        assert len(d["levels"]) == 2


# ===========================================================================
# TelemetryTracker
# ===========================================================================


class TestTelemetryTracker:
    """Tests para TelemetryTracker — gestión de sesiones y exportación."""

    def test_start_session(self, tracker: TelemetryTracker) -> None:
        """start_session: crea y almacena una SessionTelemetry."""
        t = tracker.start_session("s1", "task1", project="proj")
        assert t.session_id == "s1"
        assert t.task == "task1"
        assert t.project == "proj"
        assert t.status == "running"
        assert tracker.get_session("s1") is t

    def test_start_session_default_project(self, tracker: TelemetryTracker) -> None:
        """start_session: project por defecto vacío."""
        t = tracker.start_session("s1", "task1")
        assert t.project == ""

    def test_get_session_missing(self, tracker: TelemetryTracker) -> None:
        """get_session: sesión inexistente → None."""
        assert tracker.get_session("ghost") is None

    def test_list_sessions(self, tracker: TelemetryTracker) -> None:
        """list_sessions: retorna todas las session_ids."""
        tracker.start_session("s1", "t1")
        tracker.start_session("s2", "t2")
        ids = tracker.list_sessions()
        assert sorted(ids) == ["s1", "s2"]

    def test_list_sessions_empty(self, tracker: TelemetryTracker) -> None:
        """list_sessions: sin sesiones → lista vacía."""
        assert tracker.list_sessions() == []

    def test_finalize_session(self, tracker: TelemetryTracker) -> None:
        """finalize_session: finaliza y exporta la sesión."""
        tracker.start_session("s1", "t1")
        tracker.finalize_session("s1", status="completed")
        t = tracker.get_session("s1")
        assert t is not None
        assert t.status == "completed"
        assert t.end_time > 0
        # Archivo exportado
        export_file = tracker._export_dir / "telemetry_s1.json"
        assert export_file.exists()

    def test_finalize_session_missing(self, tracker: TelemetryTracker) -> None:
        """finalize_session: sesión inexistente no lanza error."""
        tracker.finalize_session("ghost")  # no error

    def test_export_session(self, tracker: TelemetryTracker) -> None:
        """export: escribe JSON con contenido válido."""
        tracker.start_session("s1", "t1")
        path = tracker.export("s1")
        assert path is not None
        assert Path(path).exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["session_id"] == "s1"

    def test_export_missing_session(self, tracker: TelemetryTracker) -> None:
        """export: sesión inexistente → None."""
        assert tracker.export("ghost") is None

    def test_export_all(self, tracker: TelemetryTracker) -> None:
        """export_all: exporta todas las sesiones."""
        tracker.start_session("s1", "t1")
        tracker.start_session("s2", "t2")
        paths = tracker.export_all()
        assert len(paths) == 2
        for p in paths:
            assert Path(p).exists()

    def test_export_all_empty(self, tracker: TelemetryTracker) -> None:
        """export_all: sin sesiones → lista vacía."""
        assert tracker.export_all() == []

    def test_export_summary(self, tracker: TelemetryTracker) -> None:
        """export_summary: escribe resumen de todas las sesiones."""
        tracker.start_session("s1", "t1", project="p1")
        tracker.finalize_session("s1", status="completed")
        path = tracker.export_summary()
        assert Path(path).exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["total_sessions"] == 1
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == "s1"

    def test_export_summary_empty(self, tracker: TelemetryTracker) -> None:
        """export_summary: sin sesiones → sesiones vacío."""
        path = tracker.export_summary()
        assert Path(path).exists()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["total_sessions"] == 0
        assert data["sessions"] == []

    def test_load_all(self, tracker: TelemetryTracker) -> None:
        """load_all: carga sesiones desde archivos JSON."""
        tracker.start_session("s1", "t1", project="p1")
        tracker.export("s1")
        # Crear un segundo tracker con el mismo directorio temporal
        tracker2 = TelemetryTracker(export_dir=str(tracker._export_dir))
        loaded = tracker2.load_all()
        assert "s1" in loaded
        assert loaded["s1"].task == "t1"
        assert loaded["s1"].project == "p1"

    def test_load_all_skips_summary(self, tracker: TelemetryTracker) -> None:
        """load_all: salta telemetry_summary.json."""
        tracker.start_session("s1", "t1")
        tracker.export("s1")
        tracker.export_summary()
        tracker2 = TelemetryTracker(export_dir=str(tracker._export_dir))
        loaded = tracker2.load_all()
        assert "s1" in loaded

    def test_load_all_empty_dir(self, tracker: TelemetryTracker) -> None:
        """load_all: directorio sin archivos → dict vacío."""
        loaded = tracker.load_all()
        assert loaded == {}

    def test_clear(self, tracker: TelemetryTracker) -> None:
        """clear: limpia sesiones en memoria sin borrar archivos."""
        tracker.start_session("s1", "t1")
        tracker.export("s1")
        tracker.clear()
        assert tracker.list_sessions() == []
        # Archivos aún existen
        assert list(tracker._export_dir.glob("telemetry_*.json"))

    def test_export_dir_created(self, tmp_path: Path) -> None:
        """__init__: crea el directorio de export si no existe."""
        new_dir = tmp_path / "nested" / "telemetry"
        tracker = TelemetryTracker(export_dir=str(new_dir))
        assert new_dir.exists()


# ===========================================================================
# track_subtask decorator
# ===========================================================================


class TestTrackSubtaskDecorator:
    """Tests para el decorador @track_subtask."""

    def test_track_success(self, tracker: TelemetryTracker) -> None:
        """track_subtask: registra subtask exitosa."""
        tracker.start_session("s1", "task1")

        @track_subtask(tracker)
        def my_agent_func(session_id: str, x: int) -> int:
            """My agent function."""
            return x * 2

        result = my_agent_func("s1", 21)
        assert result == 42

        t = tracker.get_session("s1")
        assert t is not None
        assert t.total_subtasks == 1
        # Debería estar en level 0 (único nivel)
        assert len(t.levels) == 1
        record = t.levels[0].subtasks[0]
        assert record.subtask_id == "my_agent_func"
        assert record.agent == "my"  # split por "_"
        assert record.status == "success"
        assert record.duration_ms >= 0

    def test_track_failure(self, tracker: TelemetryTracker) -> None:
        """track_subtask: registra subtask fallida."""
        tracker.start_session("s1", "task1")

        @track_subtask(tracker)
        def failing_func(session_id: str) -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing_func("s1")

        t = tracker.get_session("s1")
        assert t is not None
        record = t.levels[0].subtasks[0]
        assert record.status == "failed"
        assert record.error == "boom"
        # duration can be 0 for very fast failures
        assert record.duration_ms >= 0

    def test_track_no_session(self, tracker: TelemetryTracker) -> None:
        """track_subtask: sin sesión activa → ejecuta función sin registro."""
        @track_subtask(tracker)
        def my_func(session_id: str) -> str:
            return "ok"

        result = my_func("ghost")
        assert result == "ok"
        # No hay sesión, no hay registro

    def test_track_agent_name_no_underscore(self, tracker: TelemetryTracker) -> None:
        """track_subtask: nombre sin '_' → usa nombre completo como agent."""
        tracker.start_session("s1", "task1")

        @track_subtask(tracker)
        def tool123(session_id: str) -> str:
            return "done"

        tool123("s1")
        t = tracker.get_session("s1")
        assert t is not None
        record = t.levels[0].subtasks[0]
        assert record.agent == "tool123"

    def test_track_level_idx_negative(self, tracker: TelemetryTracker) -> None:
        """track_subtask: sin niveles previos → level_idx = 0."""
        tracker.start_session("s1", "task1")

        @track_subtask(tracker)
        def worker(session_id: str) -> str:
            return "done"

        worker("s1")
        t = tracker.get_session("s1")
        assert t is not None
        # levels[-1] sería negativo, pero el decorador lo corrige a 0
        assert len(t.levels) == 1
        # record_subtask internamente crea levels[0] si no existe
        # (while len(self.levels) <= level_idx)

    def test_track_preserves_return_value(self, tracker: TelemetryTracker) -> None:
        """track_subtask: preserva el valor de retorno."""
        tracker.start_session("s1", "task1")

        @track_subtask(tracker)
        def echo(session_id: str, msg: str) -> str:
            return f"echo: {msg}"

        result = echo("s1", "hello")
        assert result == "echo: hello"

    def test_track_no_docstring(self, tracker: TelemetryTracker) -> None:
        """track_subtask: sin docstring → usa function name como description."""
        tracker.start_session("s1", "task1")

        @track_subtask(tracker)
        def bare_func(session_id: str) -> str:
            return "bare"

        bare_func("s1")
        t = tracker.get_session("s1")
        assert t is not None
        record = t.levels[0].subtasks[0]
        assert record.description == "bare_func"


# ===========================================================================
# Integration: full lifecycle
# ===========================================================================


class TestTelemetryIntegration:
    """Tests de integración: ciclo completo de telemetría."""

    def test_full_workflow(self, tmp_path: Path) -> None:
        """Ciclo completo: start → subtasks → finalize → export → load."""
        tracker = TelemetryTracker(export_dir=str(tmp_path))
        t = tracker.start_session("int-1", "integration test", project="ci")

        # Simular ejecución
        for i in range(3):
            r = SubtaskRecord(
                subtask_id=f"st-{i}",
                agent="tester",
                description=f"step {i}",
                status="success",
                start_time=time.time(),
                end_time=time.time() + 0.1,
            )
            t.record_subtask(0, r)

        t.record_error()
        t.record_warning()

        tracker.finalize_session("int-1", status="completed")

        # Verificar export
        export_path = tracker._export_dir / "telemetry_int-1.json"
        assert export_path.exists()

        # Recargar
        tracker2 = TelemetryTracker(export_dir=str(tmp_path))
        loaded = tracker2.load_all()
        assert "int-1" in loaded
        lt = loaded["int-1"]
        assert lt.session_id == "int-1"
        assert lt.total_subtasks == 3
        assert lt.total_errors == 1
        assert lt.total_warnings == 1
        assert lt.status == "completed"
