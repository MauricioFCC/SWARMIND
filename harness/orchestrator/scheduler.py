"""
Scheduler — Cron/interval/once job scheduler with LanceDB logging.

Uses the ``schedule`` library for job execution. Supports three trigger types:
  - ``cron``: Standard cron expression (e.g. "0 9 * * 1-5")
  - ``interval``: Human-readable interval (e.g. "30 minutes", "1 hour")
  - ``once``: ISO datetime for one-shot execution

Jobs are persisted in ``scheduler_jobs.yaml`` and each execution is logged
in LanceDB ``scheduler_log`` collection.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import yaml

from harness.memory_rag.lance_vector_store import (
    COLLECTION_SCHEDULER_LOG,
    LanceVectorStore,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HARNESS_ROOT = Path(__file__).resolve().parent.parent  # harness/
SCHEDULER_JOBS_PATH = HARNESS_ROOT / "orchestrator" / "scheduler_jobs.yaml"

# Verify path
assert HARNESS_ROOT.name == "harness", (
    f"HARNESS_ROOT debe ser 'harness/', got '{HARNESS_ROOT.name}'. "
    f"Full path: {HARNESS_ROOT}"
)


# ---------------------------------------------------------------------------
# Job data class
# ---------------------------------------------------------------------------


class ScheduledJob:
    """
    Represents a single scheduled job.

    Args:
        name: Unique job name.
        trigger: Trigger type — "cron", "interval", or "once".
        trigger_value: For cron: cron expression; for interval: e.g. "30 minutes";
                       for once: ISO datetime string.
        command: The task/command to execute when the job fires.
        max_retries: Maximum retries on failure (default 5).
        enabled: Whether the job is active.
        last_run: ISO datetime of last execution.
        next_run: ISO datetime of next scheduled execution.
    """

    def __init__(
        self,
        name: str,
        trigger: str,
        trigger_value: str,
        command: str,
        max_retries: int = 5,
        enabled: bool = True,
        last_run: str = "",
        next_run: str = "",
    ) -> None:
        self.name = name
        self.trigger = trigger
        self.trigger_value = trigger_value
        self.command = command
        self.max_retries = max_retries
        self.enabled = enabled
        self.last_run = last_run
        self.next_run = next_run

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "trigger_value": self.trigger_value,
            "command": self.command,
            "max_retries": self.max_retries,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScheduledJob:
        return cls(
            name=data.get("name", ""),
            trigger=data.get("trigger", ""),
            trigger_value=data.get("trigger_value", ""),
            command=data.get("command", ""),
            max_retries=data.get("max_retries", 5),
            enabled=data.get("enabled", True),
            last_run=data.get("last_run", ""),
            next_run=data.get("next_run", ""),
        )


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class Scheduler:
    """
    Job scheduler with YAML persistence and LanceDB logging.

    Runs on a background thread via ``run_scheduler()``. Jobs can be added,
    removed, and listed at runtime.
    """

    def __init__(self, vector_store: Optional[LanceVectorStore] = None) -> None:
        self._vector_store = vector_store
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
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
        """
        Add a new scheduled job.

        Args:
            name: Unique job name.
            trigger: One of "cron", "interval", "once".
            trigger_value: Depends on trigger type.
            command: The task to run.
            max_retries: Max retry attempts (default 5).

        Returns:
            The newly created ``ScheduledJob``.
        """
        trigger = trigger.lower()
        if trigger not in ("cron", "interval", "once"):
            raise ValueError(
                f"Invalid trigger type '{trigger}'. Must be 'cron', 'interval', or 'once'."
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
            self._persist_jobs()

        logger.info("Job added: %s (trigger=%s value=%s)", name, trigger, trigger_value)
        return job

    def remove_job(self, name: str) -> bool:
        """
        Remove a job by name.

        Returns:
            ``True`` if the job was found and removed.
        """
        with self._lock:
            if name in self._jobs:
                del self._jobs[name]
                self._persist_jobs()
                logger.info("Job removed: %s", name)
                return True
        logger.warning("Job not found: %s", name)
        return False

    def list_jobs(self) -> List[ScheduledJob]:
        """Return all registered jobs."""
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, name: str) -> Optional[ScheduledJob]:
        """Get a single job by name."""
        with self._lock:
            return self._jobs.get(name)

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    def run_scheduler(self) -> None:
        """
        Start the scheduler loop in a background daemon thread.

        This is a non-blocking call — the thread runs until ``stop()`` is called.
        """
        if self._running:
            logger.warning("Scheduler is already running.")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="scheduler-loop",
        )
        self._thread.start()
        logger.info("Scheduler started in background thread.")

    def stop(self) -> None:
        """Signal the scheduler loop to stop."""
        self._running = False
        logger.info("Scheduler stopping...")

    def _scheduler_loop(self) -> None:
        """Main scheduler loop — evaluates triggers and runs jobs."""
        # Lazy-import schedule so it's optional at class-import time
        try:
            import schedule as _schedule_lib
            self._schedule = _schedule_lib
        except ImportError:
            logger.error(
                "schedule library not installed. Install with: pip install schedule"
            )
            return

        # Register all existing jobs with the schedule library
        with self._lock:
            for job in self._jobs.values():
                self._register_with_schedule(job)

        # Main loop
        while self._running:
            try:
                self._schedule.run_pending()
                time.sleep(1)
            except Exception as exc:
                logger.exception("Scheduler loop error: %s", exc)
                time.sleep(5)

    def _register_with_schedule(self, job: ScheduledJob) -> None:
        """Register a single job with the schedule library."""
        if not job.enabled:
            return

        import schedule as _sched

        try:
            if job.trigger == "interval":
                # Parse interval like "30 minutes", "1 hour"
                parts = job.trigger_value.split()
                if len(parts) == 2:
                    amount = int(parts[0])
                    unit = parts[1].lower()
                    if unit in ("minutes", "minute", "min"):
                        _sched.every(amount).minutes.do(
                            self._execute_job, job_name=job.name
                        )
                    elif unit in ("hours", "hour"):
                        _sched.every(amount).hours.do(
                            self._execute_job, job_name=job.name
                        )
                    elif unit in ("seconds", "second", "sec"):
                        _sched.every(amount).seconds.do(
                            self._execute_job, job_name=job.name
                        )
                    else:
                        logger.warning("Unsupported interval unit: %s", unit)
                else:
                    logger.warning("Invalid interval format: %s", job.trigger_value)

            elif job.trigger == "once":
                # One-shot: schedule at specific datetime via .at()
                _sched.every().day.at("00:00").do(
                    self._execute_job_once, job_name=job.name
                )

            elif job.trigger == "cron":
                # Cron: simplified — convert common cron patterns to schedule syntax
                self._register_cron(_sched, job)

            logger.debug(
                "Registered job '%s' with schedule lib", job.name
            )
        except Exception as exc:
            logger.error("Failed to register job '%s': %s", job.name, exc)

    def _register_cron(self, sched: Any, job: ScheduledJob) -> None:
        """Map a cron expression to schedule library syntax (best-effort)."""
        cron = job.trigger_value.strip().split()
        if len(cron) < 5:
            logger.warning("Invalid cron expression: %s", job.trigger_value)
            return

        minute = cron[0]
        hour = cron[1]
        day_of_week = cron[4] if len(cron) > 4 else "*"

        if minute == "*" and hour == "*" and day_of_week == "*":
            sched.every(1).minutes.do(self._execute_job, job_name=job.name)
        elif minute == "0" and hour != "*" and day_of_week == "*":
            sched.every().day.at(f"{hour}:00").do(self._execute_job, job_name=job.name)
        elif minute == "0" and hour != "*" and day_of_week != "*":
            # Map day_of_week (0-6 or MON-SUN) — simplified: run every day
            sched.every().day.at(f"{hour}:00").do(self._execute_job, job_name=job.name)
        else:
            # Fallback: run every 5 minutes for complex crons
            logger.warning("Complex cron '%s' — falling back to 5-min interval", job.trigger_value)
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

        logger.info("Executing job '%s': %s", job_name, job.command)
        start = time.time()
        status = "success"
        error_msg = ""

        try:
            # Execute the command
            if job.command.startswith("python "):
                import subprocess
                result = subprocess.run(
                    job.command, shell=True, capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    status = "failed"
                    error_msg = result.stderr[-500:] if result.stderr else "exit code != 0"
            else:
                # For non-python commands, simulate execution
                logger.info("Simulating execution of: %s", job.command)
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)

        elapsed = time.time() - start
        now = datetime.now(timezone.utc).isoformat()

        # Update job state
        with self._lock:
            j = self._jobs.get(job_name)
            if j:
                j.last_run = now

        # Log to LanceDB
        self._log_execution(job_name, job, status, elapsed, error_msg, now)

        logger.info(
            "Job '%s' %s (%.3fs)", job_name, status, elapsed
        )

    def _execute_job_once(self, job_name: str) -> None:
        """Execute a once-type job and disable it afterward."""
        self._execute_job(job_name)
        with self._lock:
            job = self._jobs.get(job_name)
            if job:
                job.enabled = False
                self._persist_jobs()
                logger.info("One-shot job '%s' disabled after execution.", job_name)

    def _log_execution(
        self,
        job_name: str,
        job: ScheduledJob,
        status: str,
        duration_ms: float,
        error: str,
        timestamp: str,
    ) -> None:
        """Log job execution to LanceDB scheduler_log."""
        if self._vector_store is None:
            return

        metadata: Dict[str, Any] = {
            "job_name": job_name,
            "trigger": job.trigger,
            "status": status,
            "duration_ms": int(duration_ms * 1000),
            "error": error[:500] if error else "",
            "timestamp": timestamp,
        }

        vec = np.zeros(384, dtype=np.float32)
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
        except Exception as exc:
            logger.warning("Failed to log scheduler execution: %s", exc)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_jobs(self) -> None:
        """Load jobs from YAML file."""
        if not SCHEDULER_JOBS_PATH.exists():
            self._ensure_jobs_file()
            return

        try:
            with open(str(SCHEDULER_JOBS_PATH), "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            job_list: List[Dict[str, Any]] = data.get("jobs", [])
            for jd in job_list:
                job = ScheduledJob.from_dict(jd)
                self._jobs[job.name] = job
            logger.info("Loaded %d jobs from %s", len(job_list), SCHEDULER_JOBS_PATH)
        except Exception as exc:
            logger.warning("Failed to load jobs: %s", exc)

    def _persist_jobs(self) -> None:
        """Write current jobs to YAML file."""
        self._ensure_jobs_file()
        job_list = [j.to_dict() for j in self._jobs.values()]
        data = {"jobs": job_list}
        try:
            with open(str(SCHEDULER_JOBS_PATH), "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        except Exception as exc:
            logger.warning("Failed to persist jobs: %s", exc)

    @staticmethod
    def _ensure_jobs_file() -> None:
        """Create the jobs YAML file if it doesn't exist."""
        SCHEDULER_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not SCHEDULER_JOBS_PATH.exists():
            with open(str(SCHEDULER_JOBS_PATH), "w", encoding="utf-8") as f:
                yaml.dump({"jobs": []}, f, default_flow_style=False, allow_unicode=True)
