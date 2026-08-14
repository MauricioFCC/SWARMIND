"""``SimpleScheduler`` — scheduler basado en cron con persistencia JSON.

Extracción mecánica desde ``harness/scheduler.py`` (sin cambios de lógica).

``croniter``, ``HAS_CRONITER`` y ``logger`` se resuelven vía el paquete en
tiempo de llamada (``import harness.scheduler as _pkg``) para que
``patch("harness.scheduler.croniter")``, ``patch("harness.scheduler.HAS_CRONITER")``
y ``patch("harness.scheduler.logger")`` sigan funcionando idéntico.
``time`` se resuelve por el módulo global (el parche de los tests se aplica
sobre el objeto real ``time`` vía ``harness.scheduler.time``).
"""

from __future__ import annotations

import datetime
import time

import harness.scheduler as _pkg

from .base import BaseScheduler
from .job_store import JobStore
from .scheduled_job import ScheduledJob


class SimpleScheduler(BaseScheduler, JobStore):
    """Cron-based task scheduler with JSON persistence.

    Uses ``croniter`` for cron expression parsing when available.
    Provides a blocking :meth:`run_loop` for the main event loop.

    Default jobs file: ``harness/scheduler_jobs.json``
    """

    def __init__(self, jobs_path: str = "") -> None:
        self._jobs_path: str = jobs_path or _pkg._DEFAULT_SIMPLE_JOBS_PATH
        self._jobs: dict[str, ScheduledJob] = {}
        self._running: bool = False
        self._poll_interval: int = 60
        self._load_jobs()

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(
        self,
        name: str,
        cron_expr: str,
        task_description: str,
    ) -> ScheduledJob:
        """Register a new scheduled job.

        Args:
            name: Unique identifier for the job.
            cron_expr: Cron expression (e.g. ``'0 */2 * * *'`` for every 2 hours).
            task_description: Description of the task to execute.

        Returns:
            The newly created :class:`ScheduledJob`.

        Raises:
            ValueError: If a job with the same *name* already exists.
        """
        if name in self._jobs:
            raise ValueError(f"Job '{name}' already exists")

        next_run = self._compute_next_run(cron_expr)
        job = ScheduledJob(
            name=name,
            cron_expr=cron_expr,
            task_description=task_description,
            next_run=next_run,
        )
        self._jobs[name] = job
        self._save_jobs()
        _pkg.logger.info("Scheduled job '%s': %s (next run: %s)", name, cron_expr, next_run)
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job by name.

        Returns ``True`` if the job was removed, ``False`` if it did not exist.
        """
        if name not in self._jobs:
            return False
        del self._jobs[name]
        self._save_jobs()
        _pkg.logger.info("Removed scheduled job '%s'", name)
        return True

    def list_jobs(self) -> list[ScheduledJob]:
        """Return all registered scheduled jobs."""
        return list(self._jobs.values())

    def get_job(self, name: str) -> ScheduledJob | None:
        """Return a specific job by name, or ``None``."""
        return self._jobs.get(name)

    def stop(self) -> None:
        """Signal the scheduler loop to stop at the next check cycle."""
        self._running = False
        _pkg.logger.info("Scheduler stop requested")

    # ------------------------------------------------------------------
    # Scheduling logic
    # ------------------------------------------------------------------

    def _compute_next_run(self, cron_expr: str) -> str:
        """Compute the next run datetime from a cron expression.

        Returns an ISO-formatted datetime string, or an empty string on failure.
        """
        if _pkg.HAS_CRONITER:
            try:
                base = datetime.datetime.now(datetime.UTC)
                cron = _pkg.croniter(cron_expr, base)
                next_dt = cron.get_next(datetime.datetime)
                return next_dt.isoformat()
            except (ValueError, KeyError) as exc:
                _pkg.logger.warning("Invalid cron expression '%s': %s", cron_expr, exc)
        return ""

    def run_due(self) -> list[str]:
        """Execute all jobs whose scheduled time has passed.

        Returns a list of job names that were executed.
        """
        now = datetime.datetime.now(datetime.UTC)
        executed: list[str] = []

        for job in list(self._jobs.values()):
            if not job.enabled:
                continue
            if not job.next_run:
                continue

            try:
                next_dt = datetime.datetime.fromisoformat(job.next_run)
            except (ValueError, TypeError):
                continue

            if now >= next_dt:
                self._execute_job(job)
                job.run_count += 1
                job.last_run = now.isoformat()
                job.next_run = self._compute_next_run(job.cron_expr)
                executed.append(job.name)

        if executed:
            self._save_jobs()

        return executed

    def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a single job (log-level only for SimpleScheduler)."""
        _pkg.logger.info(
            "Executing scheduled job '%s': %s",
            job.name,
            job.task_description,
        )

    def run_loop(self, poll_interval: int | None = None) -> None:
        """Start the scheduler loop, checking for due jobs periodically.

        This method **blocks indefinitely**.  Set *poll_interval* to override
        the default 60-second check interval.

        To stop the loop, call :meth:`stop` from another thread.
        """
        if poll_interval is not None:
            self._poll_interval = poll_interval

        self._running = True
        _pkg.logger.info(
            "Scheduler loop started (poll interval: %ds)", self._poll_interval,
        )

        try:
            while self._running:
                executed = self.run_due()
                if executed:
                    _pkg.logger.info("Executed %d job(s): %s", len(executed), executed)
                time.sleep(self._poll_interval)
        except KeyboardInterrupt:
            _pkg.logger.info("Scheduler loop interrupted by user")
            self._running = False
        except Exception:  # noqa: BLE001 — loggeado vía _pkg.logger.exception (intención del módulo original)
            _pkg.logger.exception("Scheduler loop error")
            self._running = False
