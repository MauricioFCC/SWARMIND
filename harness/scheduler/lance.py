"""``LanceScheduler`` — scheduler con schedule-lib, persistencia YAML y LanceDB.

Extracción mecánica desde ``harness/scheduler.py`` (sin cambios de lógica).

``logger`` y ``EMBEDDING_DIM`` se resuelven vía el paquete en tiempo de
llamada (``import harness.scheduler as _pkg``) para que
``patch("harness.scheduler.logger")`` y la inyección dinámica
``harness.scheduler.EMBEDDING_DIM`` de los tests sigan funcionando idéntico.
"""

from __future__ import annotations

import datetime
import threading
import time
from typing import Any

import harness.scheduler as _pkg

from .base import BaseScheduler
from .job_store import JobStore
from .scheduled_job import ScheduledJob


class LanceScheduler(BaseScheduler, JobStore):
    """Job scheduler with YAML persistence and optional LanceDB logging.

    Uses the ``schedule`` library for job execution.  Supports three trigger
    types:

    - **cron**: Standard cron expression (e.g. ``"0 9 * * 1-5"``)
    - **interval**: Human-readable interval (e.g. ``"30 minutes"``, ``"1 hour"``)
    - **once**: ISO datetime for one-shot execution

    Jobs are persisted in ``orchestrator/scheduler_jobs.yaml`` and each
    execution is optionally logged in LanceDB.
    """

    def __init__(self, vector_store: Any = None, jobs_path: str = "") -> None:
        """Initialize the LanceScheduler.

        Args:
            vector_store: Optional ``LanceVectorStore`` instance for
                          execution logging.  Can be ``None`` to disable logging.
            jobs_path: Path to the YAML jobs file.  Defaults to
                       ``harness/orchestrator/scheduler_jobs.yaml``.
        """
        self._vector_store = vector_store
        self._jobs_path: str = jobs_path or _pkg._DEFAULT_LANCE_JOBS_PATH
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._schedule: Any = None  # lazy import
        self._load_jobs()

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(
        self,
        name: str,
        trigger: str,
        trigger_value: str,
        command: str,
        max_retries: int = 5,
    ) -> ScheduledJob:
        """Add a new scheduled job.

        Args:
            name: Unique job name.
            trigger: One of ``"cron"``, ``"interval"``, ``"once"``.
            trigger_value: Depends on *trigger* type.
            command: The task to run.
            max_retries: Max retry attempts (default 5).

        Returns:
            The newly created :class:`ScheduledJob`.
        """
        trigger = trigger.lower()
        if trigger not in ("cron", "interval", "once"):
            raise ValueError(
                f"Invalid trigger type '{trigger}'. "
                f"Must be 'cron', 'interval', or 'once'.",
            )

        job = ScheduledJob(
            name=name,
            trigger=trigger,
            trigger_value=trigger_value,
            command=command,
            max_retries=max_retries,
        )

        with self._lock:
            self._jobs[name] = job
            self._save_jobs()

        _pkg.logger.info(
            "Job added: %s (trigger=%s value=%s)", name, trigger, trigger_value,
        )
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a job by name.

        Returns:
            ``True`` if the job was found and removed.
        """
        with self._lock:
            if name in self._jobs:
                del self._jobs[name]
                self._save_jobs()
                _pkg.logger.info("Job removed: %s", name)
                return True
        _pkg.logger.warning("Job not found: %s", name)
        return False

    def list_jobs(self) -> list[ScheduledJob]:
        """Return all registered jobs."""
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, name: str) -> ScheduledJob | None:
        """Get a single job by name."""
        with self._lock:
            return self._jobs.get(name)

    def stop(self) -> None:
        """Signal the scheduler loop to stop."""
        self._running = False
        _pkg.logger.info("Scheduler stopping...")

    # ------------------------------------------------------------------
    # Serialization overrides — YAML uses {"jobs": [...]} format
    # ------------------------------------------------------------------

    def _serialize_jobs(self) -> dict[str, Any]:
        return {"jobs": [j.to_dict() for j in self._jobs.values()]}

    def _deserialize_jobs(self, data: dict[str, Any]) -> None:
        for jd in data.get("jobs", []):
            job = ScheduledJob.from_dict(jd)
            self._jobs[job.name] = job

    def _default_empty_data(self) -> dict[str, Any]:
        return {"jobs": []}

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    def run_scheduler(self) -> None:
        """Start the scheduler loop in a background daemon thread.

        This is a **non-blocking** call — the thread runs until
        :meth:`stop` is called.
        """
        if self._running:
            _pkg.logger.warning("Scheduler is already running.")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="scheduler-loop",
        )
        self._thread.start()
        _pkg.logger.info("Scheduler started in background thread.")

    def _scheduler_loop(self) -> None:
        """Main scheduler loop — evaluates triggers and runs jobs."""
        # Lazy-import schedule so it's optional at class-import time
        try:
            import schedule as _schedule_lib  # type: ignore[import-untyped]
            self._schedule = _schedule_lib
        except ImportError:
            _pkg.logger.error(
                "schedule library not installed.  Install with: pip install schedule",
            )
            return

        # Register all existing jobs with the schedule library
        with self._lock:
            for job in self._jobs.values():
                self._register_with_schedule(job)

        while self._running:
            try:
                self._schedule.run_pending()
                time.sleep(1)
            except Exception:  # noqa: BLE001 — loggeado vía _pkg.logger.exception (intención del módulo original)
                _pkg.logger.exception("Scheduler loop error")
                time.sleep(5)

    def _register_with_schedule(self, job: ScheduledJob) -> None:
        """Register a single job with the schedule library."""
        if not job.enabled:
            return

        import schedule as _sched

        try:
            if job.trigger == "interval":
                parts = job.trigger_value.split()
                if len(parts) == 2:
                    amount = int(parts[0])
                    unit = parts[1].lower()
                    if unit in ("minutes", "minute", "min"):
                        _sched.every(amount).minutes.do(
                            self._execute_job, job_name=job.name,
                        )
                    elif unit in ("hours", "hour"):
                        _sched.every(amount).hours.do(
                            self._execute_job, job_name=job.name,
                        )
                    elif unit in ("seconds", "second", "sec"):
                        _sched.every(amount).seconds.do(
                            self._execute_job, job_name=job.name,
                        )
                    else:
                        _pkg.logger.warning("Unsupported interval unit: %s", unit)
                else:
                    _pkg.logger.warning("Invalid interval format: %s", job.trigger_value)

            elif job.trigger == "once":
                _sched.every().day.at("00:00").do(
                    self._execute_job_once, job_name=job.name,
                )

            elif job.trigger == "cron":
                self._register_cron(_sched, job)

            _pkg.logger.debug("Registered job '%s' with schedule lib", job.name)
        except Exception as exc:  # noqa: BLE001
            _pkg.logger.error("Failed to register job '%s': %s", job.name, exc)

    def _register_cron(self, sched: Any, job: ScheduledJob) -> None:
        """Map a cron expression to schedule library syntax (best-effort)."""
        cron_parts = job.trigger_value.strip().split()
        if len(cron_parts) < 5:
            _pkg.logger.warning("Invalid cron expression: %s", job.trigger_value)
            return

        minute = cron_parts[0]
        hour = cron_parts[1]
        day_of_week = cron_parts[4] if len(cron_parts) > 4 else "*"

        if minute == "*" and hour == "*" and day_of_week == "*":
            sched.every(1).minutes.do(self._execute_job, job_name=job.name)
        elif minute == "0" and hour != "*" and day_of_week == "*" or minute == "0" and hour != "*" and day_of_week != "*":
            sched.every().day.at(f"{hour}:00").do(
                self._execute_job, job_name=job.name,
            )
        else:
            _pkg.logger.warning(
                "Complex cron '%s' — falling back to 5-min interval",
                job.trigger_value,
            )
            sched.every(5).minutes.do(self._execute_job, job_name=job.name)

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    def _execute_job(self, job_name: str) -> None:
        """Execute a job and log results."""
        with self._lock:
            job = self._jobs.get(job_name)
            if job is None:
                return

        _pkg.logger.info("Executing job '%s': %s", job_name, job.command)
        start = time.time()
        status = "success"
        error_msg = ""

        try:
            import shlex as _shlex
            import subprocess as _subprocess

            cmd_list = _shlex.split(job.command)
            result = _subprocess.run(
                cmd_list, capture_output=True, text=True, timeout=300, check=False,
            )
            if result.returncode != 0:
                status = "failed"
                error_msg = result.stderr[-500:] if result.stderr else "exit code != 0"
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error_msg = str(exc)

        elapsed = time.time() - start
        now = datetime.datetime.now(datetime.UTC).isoformat()

        # Update job state
        with self._lock:
            j = self._jobs.get(job_name)
            if j:
                j.last_run = now

        # Log to LanceDB
        if job is not None:
            self._log_execution(job_name, job, status, elapsed, error_msg, now)

        _pkg.logger.info("Job '%s' %s (%.3fs)", job_name, status, elapsed)

    def _execute_job_once(self, job_name: str) -> None:
        """Execute a once-type job and disable it afterward."""
        self._execute_job(job_name)
        with self._lock:
            job = self._jobs.get(job_name)
            if job:
                job.enabled = False
                self._save_jobs()
                _pkg.logger.info(
                    "One-shot job '%s' disabled after execution.", job_name,
                )

    def _log_execution(
        self,
        job_name: str,
        job: ScheduledJob,
        status: str,
        duration_ms: float,
        error: str,
        timestamp: str,
    ) -> None:
        """Log job execution to LanceDB ``scheduler_log`` collection."""
        if self._vector_store is None:
            return

        try:
            import numpy as np  # type: ignore[import-untyped]

            from harness.memory_rag.lance_vector_store import (
                COLLECTION_SCHEDULER_LOG,
            )
        except ImportError:
            _pkg.logger.debug(
                "LanceDB logging unavailable (numpy or lance_vector_store)",
            )
            return

        metadata: dict[str, Any] = {
            "job_name": job_name,
            "trigger": job.trigger,
            "status": status,
            "duration_ms": int(duration_ms * 1000),
            "error": error[:500] if error else "",
            "timestamp": timestamp,
        }

        vec = np.zeros(_pkg.EMBEDDING_DIM, dtype=np.float32)
        text_for_vec = f"{job_name} {job.command} {status}"
        for i, ch in enumerate(text_for_vec.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % 384
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        try:
            self._vector_store.insert(
                COLLECTION_SCHEDULER_LOG,
                vec.reshape(1, -1),
                [metadata],
            )
        except Exception as exc:  # noqa: BLE001
            _pkg.logger.warning(
                "Failed to log scheduler execution: %s", exc,
            )
