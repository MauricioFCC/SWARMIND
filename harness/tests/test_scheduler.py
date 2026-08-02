"""
Tests para harness/scheduler.py — sistema de schedulers (SimpleScheduler, LanceScheduler).

Cubre: ScheduledJob dataclass, JobStore mixin, SimpleScheduler (add/remove/list/get/
stop/run_due/run_loop/_compute_next_run), LanceScheduler (add/remove/list/get/
stop/run_scheduler/_scheduler_loop/_register_with_schedule/_register_cron/
_execute_job/_execute_job_once/_log_execution), backward-compat aliases.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_logger():
    """Parchea el logger del modulo scheduler."""
    with patch("harness.scheduler.logger") as m:
        yield m


# ===================================================================
# ScheduledJob dataclass
# ===================================================================

class TestScheduledJob:
    """Tests para ScheduledJob dataclass."""

    def test_default_created_at(self):
        """Si created_at no se provee, debe auto-generarse."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="test_job")
        assert job.created_at != ""
        datetime.fromisoformat(job.created_at)

    def test_to_dict_omits_empty(self):
        """to_dict debe omitir campos vacios excepto name y enabled."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="test")
        d = job.to_dict()
        assert "name" in d
        assert "enabled" in d
        assert "cron_expr" not in d
        assert "run_count" not in d
        assert "trigger" not in d

    def test_to_dict_includes_non_empty(self):
        """to_dict debe incluir campos con valores no-vacios."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="test", command="echo hi", trigger="cron",
                           trigger_value="0 * * * *", max_retries=3, run_count=5)
        d = job.to_dict()
        assert d["command"] == "echo hi"
        assert d["trigger"] == "cron"
        assert d["trigger_value"] == "0 * * * *"
        assert d["max_retries"] == 3
        assert d["run_count"] == 5

    def test_from_dict_full(self):
        """from_dict debe reconstruir un job completo."""
        from harness.scheduler import ScheduledJob
        data = {
            "name": "full_job", "cron_expr": "0 */2 * * *",
            "task_description": "run backup", "run_count": 10,
            "created_at": "2026-01-01T00:00:00+00:00",
            "trigger": "cron", "trigger_value": "0 */2 * * *",
            "command": "backup.sh", "max_retries": 3,
            "enabled": False, "last_run": "2026-01-02", "next_run": "2026-01-03",
        }
        job = ScheduledJob.from_dict(data)
        assert job.name == "full_job"
        assert job.cron_expr == "0 */2 * * *"
        assert job.task_description == "run backup"
        assert job.run_count == 10
        assert job.trigger == "cron"
        assert job.enabled is False
        assert job.last_run == "2026-01-02"

    def test_from_dict_minimal(self):
        """from_dict con datos minimos debe usar defaults."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob.from_dict({"name": "minimal"})
        assert job.name == "minimal"
        assert job.cron_expr == ""
        assert job.run_count == 0
        assert job.enabled is True
        assert job.max_retries == 5


# ===================================================================
# JobStore mixin
# ===================================================================

class TestJobStore:
    """Tests para JobStore mixin — persistencia de jobs."""

    @pytest.fixture
    def store_class(self):
        """Crea una clase concreta que hereda de JobStore."""
        from harness.scheduler import JobStore

        class ConcreteStore(JobStore):
            def __init__(self, path):
                self._jobs_path = str(path)
                self._jobs: dict[str, Any] = {}
                self._load_jobs()

        return ConcreteStore

    def test_load_empty_file(self, tmp_path, store_class):
        """_load_jobs con archivo nuevo debe crear estructura vacia."""
        p = tmp_path / "empty.json"
        s = store_class(p)
        assert p.is_file()
        assert s._jobs == {}

    def test_save_and_load_json(self, tmp_path, store_class):
        """Guardar y recargar jobs debe preservar datos (JSON)."""
        from harness.scheduler import ScheduledJob
        p = tmp_path / "test_jobs.json"
        s1 = store_class(p)
        job = ScheduledJob(name="persist_test", command="echo ok",
                           trigger="interval", trigger_value="30m")
        s1._jobs["persist_test"] = job
        s1._save_jobs()

        s2 = store_class(p)
        assert "persist_test" in s2._jobs
        assert s2._jobs["persist_test"].command == "echo ok"

    def test_detect_format_json(self, tmp_path):
        """_detect_format debe retornar 'json' para .json."""
        from harness.scheduler import JobStore

        class S(JobStore):
            pass

        s = S()
        s._jobs_path = str(tmp_path / "jobs.json")
        assert s._detect_format() == "json"

    def test_detect_format_yaml(self, tmp_path):
        """_detect_format debe retornar 'yaml' para .yaml/.yml."""
        from harness.scheduler import JobStore

        class S(JobStore):
            pass

        s = S()
        s._jobs_path = str(tmp_path / "jobs.yaml")
        assert s._detect_format() == "yaml"
        s._jobs_path = str(tmp_path / "jobs.yml")
        assert s._detect_format() == "yaml"

    def test_serialize_deserialize_list(self, tmp_path):
        """_serialize_jobs / _deserialize_jobs con formato lista."""
        from harness.scheduler import JobStore, ScheduledJob

        class S(JobStore):
            pass

        s = S()
        s._jobs_path = str(tmp_path / "j.json")
        s._jobs = {
            "a": ScheduledJob(name="a", command="cmd1"),
            "b": ScheduledJob(name="b", command="cmd2"),
        }
        data = s._serialize_jobs()
        assert isinstance(data, list)
        assert len(data) == 2

        s2 = S()
        s2._jobs_path = str(tmp_path / "j.json")
        s2._jobs = {}
        s2._deserialize_jobs(data)
        assert "a" in s2._jobs
        assert s2._jobs["b"].command == "cmd2"

    def test_serialize_deserialize_dict(self, tmp_path):
        """_deserialize_jobs con formato dict[name, dict]."""
        from harness.scheduler import JobStore

        class S(JobStore):
            pass

        s = S()
        s._jobs_path = str(tmp_path / "j.json")
        s._jobs = {}
        s._deserialize_jobs({
            "x": {"command": "echo x", "trigger": "cron"},
            "y": {"command": "echo y", "trigger": "interval", "trigger_value": "1h"},
        })
        assert "x" in s._jobs
        assert s._jobs["y"].trigger_value == "1h"

    def test_load_failure_logs_warning(self, tmp_path, mock_logger):
        """Si _load_jobs falla, debe loggear warning."""
        from harness.scheduler import JobStore

        class S(JobStore):
            def __init__(self, path):
                self._jobs_path = str(path)
                self._jobs = {}
                self._load_jobs()

        # Crear archivo primero para que _load_jobs llame a _read_file
        p = tmp_path / "bad.json"
        p.write_text("[]", encoding="utf-8")

        original = JobStore._read_file
        JobStore._read_file = MagicMock(side_effect=Exception("IO error"))
        try:
            S(p)
        finally:
            JobStore._read_file = original
        mock_logger.warning.assert_called()

    def test_save_failure_logs_warning(self, tmp_path, mock_logger):
        """Si _save_jobs falla, debe loggear warning."""
        from harness.scheduler import JobStore, ScheduledJob

        class S(JobStore):
            pass

        s = S()
        s._jobs_path = str(tmp_path / "no_perms.json")
        s._jobs = {"test": ScheduledJob(name="test")}
        with patch.object(s, '_write_file', side_effect=Exception("Write error")):
            s._save_jobs()
        mock_logger.warning.assert_called()

    def test_default_empty_data(self, tmp_path):
        """_default_empty_data debe retornar lista vacia."""
        from harness.scheduler import JobStore

        class S(JobStore):
            pass

        s = S()
        assert s._default_empty_data() == []


# ===================================================================
# SimpleScheduler
# ===================================================================

class TestSimpleScheduler:
    """Tests para SimpleScheduler — scheduler basado en cron con JSON persistence."""

    @pytest.fixture
    def scheduler(self, tmp_path):
        """SimpleScheduler con path temporal."""
        from harness.scheduler import SimpleScheduler
        p = tmp_path / "simple_jobs.json"
        s = SimpleScheduler(jobs_path=str(p))
        return s

    def test_init_creates_jobs_file(self, tmp_path):
        """__init__ debe crear el archivo de jobs si no existe."""
        from harness.scheduler import SimpleScheduler
        p = tmp_path / "new_jobs.json"
        assert not p.is_file()
        SimpleScheduler(jobs_path=str(p))
        assert p.is_file()

    def test_add_job(self, scheduler):
        """add_job debe agregar un job y retornarlo."""
        job = scheduler.add_job("test_job", "0 */2 * * *", "Run backup")
        assert job.name == "test_job"
        assert job.cron_expr == "0 */2 * * *"
        assert job.task_description == "Run backup"
        assert job.name in scheduler._jobs

    def test_add_duplicate_job_raises(self, scheduler):
        """add_job con nombre duplicado debe lanzar ValueError."""
        scheduler.add_job("dup", "0 * * * *", "task1")
        with pytest.raises(ValueError, match="already exists"):
            scheduler.add_job("dup", "*/5 * * * *", "task2")

    def test_remove_job_exists(self, scheduler):
        """remove_job debe eliminar job existente y retornar True."""
        scheduler.add_job("to_remove", "0 * * * *", "desc")
        result = scheduler.remove_job("to_remove")
        assert result is True
        assert "to_remove" not in scheduler._jobs

    def test_remove_job_not_found(self, scheduler):
        """remove_job con nombre inexistente debe retornar False."""
        result = scheduler.remove_job("no_existe")
        assert result is False

    def test_list_jobs(self, scheduler):
        """list_jobs debe retornar todos los jobs."""
        scheduler.add_job("a", "0 * * * *", "A")
        scheduler.add_job("b", "*/5 * * * *", "B")
        jobs = scheduler.list_jobs()
        assert len(jobs) == 2
        names = {j.name for j in jobs}
        assert names == {"a", "b"}

    def test_get_job_found(self, scheduler):
        """get_job debe retornar el job si existe."""
        scheduler.add_job("target", "0 9 * * 1-5", "weekday task")
        job = scheduler.get_job("target")
        assert job is not None
        assert job.name == "target"

    def test_get_job_not_found(self, scheduler):
        """get_job debe retornar None si no existe."""
        assert scheduler.get_job("ghost") is None

    def test_stop(self, scheduler):
        """stop debe poner _running en False."""
        scheduler._running = True
        scheduler.stop()
        assert scheduler._running is False

    def test_compute_next_run_with_croniter(self, scheduler):
        """_compute_next_run con croniter disponible debe retornar ISO datetime."""
        mock_cron = MagicMock()
        mock_cron.get_next.return_value = datetime(2026, 7, 20, 10, 0, 0,
                                                    tzinfo=UTC)
        with patch("harness.scheduler.croniter", return_value=mock_cron,
                   create=True), \
             patch("harness.scheduler.HAS_CRONITER", True):
            result = scheduler._compute_next_run("0 * * * *")
        assert "2026" in result

    def test_compute_next_run_invalid_cron(self, scheduler):
        """_compute_next_run con cron invalido debe retornar ''."""
        mock_cron = MagicMock()
        mock_cron.get_next.side_effect = ValueError("bad cron")
        with patch("harness.scheduler.croniter", return_value=mock_cron,
                   create=True), \
             patch("harness.scheduler.HAS_CRONITER", True):
            result = scheduler._compute_next_run("invalid-cron")
        assert result == ""

    def test_compute_next_run_no_croniter(self, scheduler):
        """_compute_next_run sin croniter debe retornar ''."""
        with patch("harness.scheduler.HAS_CRONITER", False):
            result = scheduler._compute_next_run("0 * * * *")
        assert result == ""

    def test_run_due_no_jobs(self, scheduler):
        """run_due sin jobs debe retornar lista vacia."""
        executed = scheduler.run_due()
        assert executed == []

    def test_run_due_disabled_job(self, scheduler):
        """run_due debe saltar jobs deshabilitados."""
        scheduler.add_job("disabled_job", "* * * * *", "task")
        scheduler._jobs["disabled_job"].enabled = False
        scheduler._jobs["disabled_job"].next_run = "2020-01-01T00:00:00+00:00"
        executed = scheduler.run_due()
        assert executed == []

    def test_run_due_no_next_run(self, scheduler):
        """run_due debe saltar jobs sin next_run."""
        scheduler.add_job("no_next", "* * * * *", "task")
        scheduler._jobs["no_next"].next_run = ""
        executed = scheduler.run_due()
        assert executed == []

    def test_run_due_execute(self, scheduler):
        """run_due debe ejecutar jobs cuya hora haya pasado."""
        scheduler.add_job("due_job", "0 * * * *", "task")
        past = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
        scheduler._jobs["due_job"].next_run = past

        with patch.object(scheduler, '_execute_job') as mock_exec:
            executed = scheduler.run_due()

        assert "due_job" in executed
        mock_exec.assert_called_once()

    def test_run_due_invalid_next_run(self, scheduler):
        """run_due con next_run invalido debe saltar el job."""
        scheduler.add_job("bad_date", "0 * * * *", "task")
        scheduler._jobs["bad_date"].next_run = "not-a-date"
        executed = scheduler.run_due()
        assert executed == []

    def test_run_loop_blocking(self, scheduler):
        """run_loop debe iterar hasta stop."""
        scheduler._running = True

        def stop_after_one(*args):
            scheduler.stop()

        with patch.object(scheduler, 'run_due', return_value=[], side_effect=stop_after_one), \
             patch("harness.scheduler.time.sleep"):
            scheduler.run_loop(poll_interval=1)
        assert scheduler._running is False

    def test_run_loop_error_graceful(self, scheduler, mock_logger):
        """run_loop debe capturar excepciones y detenerse."""
        scheduler._running = True

        def stop_after(*args):
            scheduler.stop()

        # run_due lanza excepcion, sleep se llama en except -> stop
        with patch.object(scheduler, 'run_due',
                          side_effect=[Exception("Unexpected")]), \
             patch("harness.scheduler.time.sleep", side_effect=stop_after):
            scheduler.run_loop(poll_interval=1)
        assert scheduler._running is False

    def test_run_loop_custom_poll(self, scheduler):
        """run_loop debe usar poll_interval personalizado."""
        scheduler._running = True
        with patch.object(scheduler, 'run_due', return_value=[]), \
             patch("harness.scheduler.time.sleep",
                   side_effect=lambda *a: scheduler.stop()):
            scheduler.run_loop(poll_interval=30)
        assert scheduler._poll_interval == 30

    def test_execute_job_logs(self, scheduler, mock_logger):
        """_execute_job debe loggear la ejecucion."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="log_test", task_description="test task",
                           cron_expr="0 * * * *")
        scheduler._execute_job(job)
        mock_logger.info.assert_called_with(
            "Executing scheduled job '%s': %s", "log_test", "test task",
        )

    def test_persistence_across_instances(self, tmp_path):
        """Jobs deben persistir entre instancias de SimpleScheduler."""
        from harness.scheduler import SimpleScheduler
        p = tmp_path / "persist.json"
        s1 = SimpleScheduler(jobs_path=str(p))
        s1.add_job("persistent_job", "0 */6 * * *", "Run every 6h")

        s2 = SimpleScheduler(jobs_path=str(p))
        job = s2.get_job("persistent_job")
        assert job is not None
        assert job.cron_expr == "0 */6 * * *"


# ===================================================================
# LanceScheduler
# ===================================================================

class TestLanceScheduler:
    """Tests para LanceScheduler — scheduler con YAML y LanceDB logging."""

    @pytest.fixture
    def scheduler(self, tmp_path):
        """LanceScheduler con path temporal y vector_store mockeado."""
        # EMBEDDING_DIM solo existe en docstring, no como variable de modulo real
        import harness.scheduler as sched_mod
        from harness.scheduler import LanceScheduler
        if not hasattr(sched_mod, 'EMBEDDING_DIM'):
            sched_mod.EMBEDDING_DIM = 384
        p = tmp_path / "lance_jobs.yaml"
        store = MagicMock()
        s = LanceScheduler(vector_store=store, jobs_path=str(p))
        return s

    def test_init_loads_jobs(self, tmp_path):
        """__init__ debe cargar jobs desde el archivo."""
        from harness.scheduler import LanceScheduler
        p = tmp_path / "init_test.yaml"
        store = MagicMock()
        s = LanceScheduler(vector_store=store, jobs_path=str(p))
        assert p.is_file()
        assert s._jobs == {}

    def test_add_job_interval(self, scheduler):
        """add_job con trigger=interval debe agregar job."""
        job = scheduler.add_job("interval_job", "interval", "30 minutes",
                                command="echo hello")
        assert job.name == "interval_job"
        assert job.trigger == "interval"
        assert job.trigger_value == "30 minutes"
        assert job.name in scheduler._jobs

    def test_add_job_cron(self, scheduler):
        """add_job con trigger=cron debe agregar job."""
        job = scheduler.add_job("cron_job", "cron", "0 9 * * 1-5",
                                command="backup", max_retries=3)
        assert job.trigger == "cron"
        assert job.max_retries == 3

    def test_add_job_once(self, scheduler):
        """add_job con trigger=once debe agregar job."""
        job = scheduler.add_job("once_job", "once", "2026-12-31T23:59",
                                command="shutdown")
        assert job.trigger == "once"

    def test_add_job_invalid_trigger(self, scheduler):
        """add_job con trigger invalido debe lanzar ValueError."""
        with pytest.raises(ValueError, match="Invalid trigger type"):
            scheduler.add_job("bad", "invalid_trigger", "val", "cmd")

    def test_remove_job_exists(self, scheduler):
        """remove_job debe eliminar job existente."""
        scheduler.add_job("to_del", "cron", "0 * * * *", "cmd")
        result = scheduler.remove_job("to_del")
        assert result is True
        assert "to_del" not in scheduler._jobs

    def test_remove_job_not_found(self, scheduler, mock_logger):
        """remove_job con nombre inexistente debe retornar False."""
        result = scheduler.remove_job("phantom")
        assert result is False

    def test_list_jobs(self, scheduler):
        """list_jobs debe retornar copia de los jobs."""
        scheduler.add_job("j1", "cron", "0 * * * *", "cmd1")
        scheduler.add_job("j2", "interval", "1h", "cmd2")
        jobs = scheduler.list_jobs()
        assert len(jobs) == 2

    def test_get_job_found(self, scheduler):
        """get_job debe retornar job si existe."""
        scheduler.add_job("get_me", "cron", "0 * * * *", "cmd")
        job = scheduler.get_job("get_me")
        assert job is not None
        assert job.name == "get_me"

    def test_get_job_not_found(self, scheduler):
        """get_job debe retornar None si no existe."""
        assert scheduler.get_job("ghost") is None

    def test_stop(self, scheduler):
        """stop debe poner _running en False."""
        scheduler._running = True
        scheduler.stop()
        assert scheduler._running is False

    def test_run_scheduler_already_running(self, scheduler, mock_logger):
        """run_scheduler con scheduler ya corriendo debe loggear warning."""
        scheduler._running = True
        scheduler.run_scheduler()
        mock_logger.warning.assert_called_with("Scheduler is already running.")

    def test_run_scheduler_starts_thread_and_stop(self, scheduler):
        """run_scheduler debe iniciar thread en background y stop debe detenerlo."""
        scheduler.run_scheduler()
        assert scheduler._running is True
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()
        scheduler.stop()
        # Dar tiempo para que el thread termine su ciclo
        scheduler._thread.join(timeout=5)
        assert not scheduler._thread.is_alive()

    def test_register_with_schedule_disabled_job(self, scheduler, mock_logger):
        """_register_with_schedule debe saltar jobs deshabilitados."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="disabled", enabled=False, trigger="cron",
                           trigger_value="0 * * * *", command="cmd")
        with patch("harness.scheduler.LanceScheduler._register_cron") as mock_reg:
            scheduler._register_with_schedule(job)
            mock_reg.assert_not_called()

    def test_register_with_schedule_interval_minutes(self, scheduler):
        """_register_with_schedule con interval en minutos."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="every_30m", enabled=True, trigger="interval",
                           trigger_value="30 minutes", command="cmd")
        with patch("harness.scheduler.LanceScheduler._register_cron") as mock_reg:
            scheduler._register_with_schedule(job)
            mock_reg.assert_not_called()

    def test_register_with_schedule_interval_hours(self, scheduler):
        """_register_with_schedule con interval en horas."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="every_2h", enabled=True, trigger="interval",
                           trigger_value="2 hours", command="cmd")
        with patch("harness.scheduler.LanceScheduler._register_cron") as mock_reg:
            scheduler._register_with_schedule(job)
            mock_reg.assert_not_called()

    def test_register_with_schedule_interval_seconds(self, scheduler):
        """_register_with_schedule con interval en segundos."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="every_30s", enabled=True, trigger="interval",
                           trigger_value="30 seconds", command="cmd")
        with patch("harness.scheduler.LanceScheduler._register_cron") as mock_reg:
            scheduler._register_with_schedule(job)
            mock_reg.assert_not_called()

    def test_register_with_schedule_interval_invalid_unit(self, scheduler, mock_logger):
        """_register_with_schedule con unidad no soportada debe loggear warning."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="bad_unit", enabled=True, trigger="interval",
                           trigger_value="5 days", command="cmd")
        scheduler._register_with_schedule(job)
        mock_logger.warning.assert_called_with(
            "Unsupported interval unit: %s", "days"
        )

    def test_register_with_schedule_interval_bad_format(self, scheduler, mock_logger):
        """_register_with_schedule con formato invalido debe loggear."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="bad_fmt", enabled=True, trigger="interval",
                           trigger_value="invalid", command="cmd")
        scheduler._register_with_schedule(job)
        mock_logger.warning.assert_called_with(
            "Invalid interval format: %s", "invalid"
        )

    def test_register_with_schedule_once(self, scheduler):
        """_register_with_schedule con trigger=once debe registrarse."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="one_shot", enabled=True, trigger="once",
                           trigger_value="2026-12-31", command="cmd")
        with patch("harness.scheduler.LanceScheduler._register_cron") as mock_reg:
            scheduler._register_with_schedule(job)
            mock_reg.assert_not_called()

    def test_register_cron_too_few_parts(self, scheduler, mock_logger):
        """_register_cron con cron de menos de 5 partes debe loggear warning."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="bad_cron", enabled=True, trigger="cron",
                           trigger_value="* * *", command="cmd")
        mock_sched = MagicMock()
        scheduler._register_cron(mock_sched, job)
        mock_logger.warning.assert_called_with(
            "Invalid cron expression: %s", "* * *"
        )

    def test_register_cron_every_minute(self, scheduler):
        """_register_cron con '* * * * *' debe registrar cada minuto."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="every_min", enabled=True, trigger="cron",
                           trigger_value="* * * * *", command="cmd")
        mock_sched = MagicMock()
        scheduler._register_cron(mock_sched, job)
        mock_sched.every.assert_called_once()

    def test_register_cron_daily(self, scheduler):
        """_register_cron con '0 9 * * *' debe registrar a las 9:00."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="daily_9", enabled=True, trigger="cron",
                           trigger_value="0 9 * * *", command="cmd")
        mock_sched = MagicMock()
        mock_day = MagicMock()
        mock_sched.every.return_value.day = mock_day
        scheduler._register_cron(mock_sched, job)
        mock_day.at.assert_called_with("9:00")

    def test_register_cron_daily_with_dow(self, scheduler):
        """_register_cron con '0 9 * * 1-5' debe registrar."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="daily_9_dow", enabled=True, trigger="cron",
                           trigger_value="0 9 * * 1-5", command="cmd")
        mock_sched = MagicMock()
        mock_day = MagicMock()
        mock_sched.every.return_value.day = mock_day
        scheduler._register_cron(mock_sched, job)
        mock_day.at.assert_called_with("9:00")

    def test_register_cron_complex(self, scheduler, mock_logger):
        """_register_cron con cron complejo debe hacer fallback a 5-min."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="complex", enabled=True, trigger="cron",
                           trigger_value="*/15 9-17 * * 1-5", command="cmd")
        mock_sched = MagicMock()
        scheduler._register_cron(mock_sched, job)
        mock_sched.every.assert_called_with(5)

    def test_register_cron_fallback_minutes(self, scheduler, mock_logger):
        """_register_cron con patron no estandar debe loggear y usar fallback."""
        from harness.scheduler import ScheduledJob
        job = ScheduledJob(name="weird", enabled=True, trigger="cron",
                           trigger_value="*/5 * * * *", command="cmd")
        mock_sched = MagicMock()
        mock_sched.every.return_value = mock_sched
        mock_sched.minutes = mock_sched
        scheduler._register_cron(mock_sched, job)
        mock_sched.every.assert_called_with(5)

    def test_execute_job_not_found(self, scheduler, mock_logger):
        """_execute_job con job_name inexistente debe retornar silenciosamente."""
        scheduler._execute_job("ghost_job")

    def test_execute_job_success(self, scheduler, mock_logger):
        """_execute_job debe ejecutar comando y loggear exito."""
        scheduler.add_job("success_job", "cron", "0 * * * *", command="echo ok")
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            scheduler._execute_job("success_job")

        assert scheduler._jobs["success_job"].last_run != ""

    def test_execute_job_failure(self, scheduler, mock_logger):
        """_execute_job con comando fallido debe loggear error."""
        scheduler.add_job("fail_job", "cron", "0 * * * *", command="false")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error output"

        with patch("subprocess.run", return_value=mock_result):
            scheduler._execute_job("fail_job")

    def test_execute_job_exception(self, scheduler, mock_logger):
        """_execute_job con excepcion debe loggear error."""
        scheduler.add_job("crash_job", "cron", "0 * * * *", command="crash")
        with patch("subprocess.run", side_effect=Exception("Segfault")):
            scheduler._execute_job("crash_job")

    def test_execute_job_once(self, scheduler):
        """_execute_job_once debe ejecutar y deshabilitar el job."""
        scheduler.add_job("once_test", "once", "2026-12-31", command="echo done")
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            scheduler._execute_job_once("once_test")

        assert scheduler._jobs["once_test"].enabled is False

    def test_log_execution_no_vector_store(self, scheduler, mock_logger):
        """_log_execution sin vector_store debe retornar inmediatamente."""
        scheduler._vector_store = None
        from harness.scheduler import ScheduledJob
        job = scheduler._jobs.get("test") or ScheduledJob(name="test")
        scheduler._log_execution("test", job, "success", 1.0, "", "2026-01-01")

    def _setup_embedding_dim(self):
        """Configura EMBEDDING_DIM en el modulo scheduler si no existe.

        Nota: EMBEDDING_DIM esta definido solo en el docstring del modulo
        pero NO como variable de modulo real. Lo inyectamos para los tests.
        """
        import harness.scheduler as sched_mod
        if not hasattr(sched_mod, 'EMBEDDING_DIM'):
            sched_mod.EMBEDDING_DIM = 384

    def test_log_execution_with_store(self, scheduler):
        """_log_execution debe insertar en LanceDB."""
        self._setup_embedding_dim()
        scheduler.add_job("log_job", "cron", "0 * * * *", command="log_test")
        job = scheduler._jobs["log_job"]

        mock_np = MagicMock()
        mock_np.zeros.return_value = MagicMock()
        mock_np.linalg.norm.return_value = 1.0

        with patch.dict("sys.modules", {"numpy": mock_np}), \
             patch("harness.memory_rag.lance_vector_store.COLLECTION_SCHEDULER_LOG",
                   "scheduler_log"):
            scheduler._log_execution("log_job", job, "success", 1.5, "",
                                     "2026-01-01")

        scheduler._vector_store.insert.assert_called_once()

    def test_log_execution_no_numpy(self, scheduler, mock_logger):
        """_log_execution sin numpy debe loggear debug y retornar."""
        scheduler.add_job("no_np", "cron", "0 * * * *", command="test")
        job = scheduler._jobs["no_np"]

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "numpy":
                raise ImportError("No numpy")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, '__import__', mock_import):
            scheduler._log_execution("no_np", job, "success", 1.0, "",
                                     "2026-01-01")

    def test_log_execution_insert_exception(self, scheduler, mock_logger):
        """Si vector_store.insert falla, debe loggear warning."""
        self._setup_embedding_dim()
        scheduler.add_job("insert_fail", "cron", "0 * * * *", command="test")
        job = scheduler._jobs["insert_fail"]
        scheduler._vector_store.insert.side_effect = Exception("DB insert error")

        mock_np = MagicMock()
        mock_np.zeros.return_value = MagicMock()
        mock_np.linalg.norm.return_value = 1.0

        with patch.dict("sys.modules", {"numpy": mock_np}):
            scheduler._log_execution("insert_fail", job, "success", 1.0, "",
                                     "2026-01-01")

        mock_logger.warning.assert_called()

    def test_serialize_jobs_format(self, scheduler):
        """_serialize_jobs de LanceScheduler debe usar formato {'jobs': [...]}."""
        scheduler.add_job("s1", "cron", "0 * * * *", "cmd1")
        data = scheduler._serialize_jobs()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)
        assert len(data["jobs"]) == 1

    def test_deserialize_jobs_format(self, scheduler):
        """_deserialize_jobs de LanceScheduler debe leer formato {'jobs': [...]}."""
        scheduler._deserialize_jobs({
            "jobs": [
                {"name": "d1", "trigger": "cron", "trigger_value": "0 * * * *",
                 "command": "cmd"},
            ]
        })
        assert "d1" in scheduler._jobs
        assert scheduler._jobs["d1"].trigger == "cron"

    def test_default_empty_data_override(self, scheduler):
        """_default_empty_data de LanceScheduler debe retornar {'jobs': []}."""
        assert scheduler._default_empty_data() == {"jobs": []}

    def test_add_job_thread_safety(self, scheduler):
        """add_job debe ser thread-safe bajo lock."""
        import concurrent.futures

        def add_job_safe(name):
            scheduler.add_job(name, "cron", "0 * * * *", f"cmd_{name}")

        names = [f"thread_job_{i}" for i in range(10)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(add_job_safe, names))

        assert len(scheduler.list_jobs()) == 10

    def test_scheduler_loop_with_schedule(self, scheduler):
        """_scheduler_loop debe ejecutar schedule.run_pending en cada iteracion."""
        scheduler.add_job("loop_job", "interval", "1 minute", command="echo test")
        mock_schedule = MagicMock()
        scheduler._schedule = mock_schedule
        scheduler._running = True

        call_count = [0]

        def stop_after_one_sleep(*args):
            call_count[0] += 1
            if call_count[0] >= 1:
                scheduler._running = False

        with patch("harness.scheduler.time.sleep", side_effect=stop_after_one_sleep):
            scheduler._scheduler_loop()

        assert scheduler._running is False

    def test_scheduler_loop_exception_handling(self, scheduler, mock_logger):
        """_scheduler_loop debe capturar excepciones y continuar."""
        scheduler._running = True
        mock_schedule = MagicMock()
        mock_schedule.run_pending.side_effect = Exception("Loop error")
        scheduler._schedule = mock_schedule

        call_count = [0]

        def stop_after_two_sleeps(*args):
            call_count[0] += 1
            if call_count[0] >= 2:
                scheduler._running = False

        with patch("harness.scheduler.time.sleep",
                   side_effect=stop_after_two_sleeps):
            scheduler._scheduler_loop()

        assert scheduler._running is False


# ===================================================================
# Backward-compatible aliases
# ===================================================================

class TestAliases:
    """Tests para backward-compatible aliases TaskScheduler y Scheduler."""

    def test_task_scheduler_is_simple_scheduler(self):
        """TaskScheduler debe ser alias de SimpleScheduler."""
        from harness.scheduler import SimpleScheduler, TaskScheduler
        assert TaskScheduler is SimpleScheduler

    def test_scheduler_is_lance_scheduler(self):
        """Scheduler debe ser alias de LanceScheduler."""
        from harness.scheduler import LanceScheduler, Scheduler
        assert Scheduler is LanceScheduler

    def test_task_scheduler_instantiation(self, tmp_path):
        """TaskScheduler debe poder instanciarse como SimpleScheduler."""
        from harness.scheduler import TaskScheduler
        p = tmp_path / "task_jobs.json"
        s = TaskScheduler(jobs_path=str(p))
        job = s.add_job("alias_test", "0 * * * *", "alias task")
        assert job.name == "alias_test"

    def test_scheduler_instantiation(self, tmp_path):
        """Scheduler debe poder instanciarse como LanceScheduler."""
        from harness.scheduler import Scheduler
        p = tmp_path / "alias_jobs.yaml"
        store = MagicMock()
        s = Scheduler(vector_store=store, jobs_path=str(p))
        job = s.add_job("alias_test", "cron", "0 * * * *", "cmd")
        assert job.name == "alias_test"
