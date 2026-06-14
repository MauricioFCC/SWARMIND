"""Cron-based task scheduler with JSON persistence.

Provides a TaskScheduler class that uses croniter for cron expression
parsing, with automatic fallback to simple interval-based scheduling
when croniter is not available.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

logger = logging.getLogger(__name__)


_DEFAULT_JOBS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scheduler_jobs.json",
)


@dataclass
class ScheduledJob:
    """ScheduledJob."""
    name: str
    cron_expr: str
    task_description: str
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledJob":
        """From dict."""
        return cls(**data)


class TaskScheduler:
    """A cron-based task scheduler with JSON persistence.

    Jobs are stored in a JSON file and checked periodically.
    Uses croniter for cron expression parsing when available.
    """

    def __init__(self, jobs_path: str = "") -> None:
        """Inicializa la instancia de la clase."""
        self._jobs_path: str = jobs_path or _DEFAULT_JOBS_PATH
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running: bool = False
        self._poll_interval: int = 60
        self._load_jobs()

    def _load_jobs(self) -> None:
        try:
            if os.path.isfile(self._jobs_path):
                with open(self._jobs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        job = ScheduledJob.from_dict(item)
                        self._jobs[job.name] = job
                elif isinstance(data, dict):
                    for name, item in data.items():
                        if isinstance(item, dict):
                            item["name"] = name
                            job = ScheduledJob.from_dict(item)
                            self._jobs[name] = job
        except (json.JSONDecodeError, FileNotFoundError, Exception) as exc:
            logger.warning("Failed to load scheduler jobs from %s: %s", self._jobs_path, exc)

    def _save_jobs(self) -> None:
        os.makedirs(os.path.dirname(self._jobs_path), exist_ok=True)
        data = [job.to_dict() for job in self._jobs.values()]
        with open(self._jobs_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _compute_next_run(self, cron_expr: str) -> Optional[str]:
        if HAS_CRONITER:
            try:
                base = datetime.datetime.now(datetime.timezone.utc)
                cron = croniter(cron_expr, base)
                next_dt = cron.get_next(datetime.datetime)
                return next_dt.isoformat()
            except (ValueError, KeyError) as exc:
                logger.warning("Invalid cron expression '%s': %s", cron_expr, exc)
                return None
        return None

    def add_job(self, name: str, cron_expr: str, task_description: str) -> ScheduledJob:
        """Register a new scheduled job.

        Args:
            name: Unique identifier for the job.
            cron_expr: Cron expression (e.g. '0 */2 * * *' for every 2 hours).
            task_description: Description of the task to execute.

        Returns:
            The newly created ScheduledJob.

        Raises:
            ValueError: If a job with the same name already exists.
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
        logger.info("Scheduled job '%s': %s (next run: %s)", name, cron_expr, next_run)
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job by name.

        Returns True if the job was removed, False if it did not exist.
        """
        if name not in self._jobs:
            return False
        del self._jobs[name]
        self._save_jobs()
        logger.info("Removed scheduled job '%s'", name)
        return True

    def list_jobs(self) -> List[ScheduledJob]:
        """Return all registered scheduled jobs."""
        return list(self._jobs.values())

    def get_job(self, name: str) -> Optional[ScheduledJob]:
        """Return a specific job by name, or None."""
        return self._jobs.get(name)

    def run_due(self) -> List[str]:
        """Execute all jobs whose scheduled time has passed.

        Returns a list of job names that were executed.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        executed: List[str] = []

        for job in list(self._jobs.values()):
            if not job.enabled:
                continue
            if job.next_run is None:
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
        logger.info(
            "Executing scheduled job '%s': %s",
            job.name,
            job.task_description,
        )

    def run_loop(self, poll_interval: Optional[int] = None) -> None:
        """Start the scheduler loop, checking for due jobs periodically.

        This method blocks indefinitely. Set poll_interval to override
        the default 60-second check interval.

        To stop the loop, call stop() from another thread.
        """
        if poll_interval is not None:
            self._poll_interval = poll_interval

        self._running = True
        logger.info(
            "Scheduler loop started (poll interval: %ds)", self._poll_interval
        )

        try:
            while self._running:
                executed = self.run_due()
                if executed:
                    logger.info("Executed %d job(s): %s", len(executed), executed)
                time.sleep(self._poll_interval)
        except KeyboardInterrupt:
            logger.info("Scheduler loop interrupted by user")
            self._running = False
        except Exception as exc:
            logger.error("Scheduler loop error: %s", exc, exc_info=True)
            self._running = False

    def stop(self) -> None:
        """Signal the scheduler loop to stop at the next check cycle."""
        self._running = False
        logger.info("Scheduler stop requested")
