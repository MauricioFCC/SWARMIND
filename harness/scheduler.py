"""

EMBEDDING_DIM = 384
Unified scheduler — BaseScheduler ABC + JobStore mixin + concrete implementations.

Provides:
  - :class:`BaseScheduler`: Abstract base with add_job, remove_job, list_jobs, get_job, stop
  - :class:`JobStore`: Mixin for JSON/YAML auto-detecting persistence
  - :class:`ScheduledJob`: Unified dataclass supporting both Simple/Lance schemas
  - :class:`SimpleScheduler`: Cron-based scheduler with JSON persistence
  - :class:`LanceScheduler`: Schedule-library-based scheduler with YAML persistence
                             and optional LanceDB logging
  - ``TaskScheduler``: Alias for ``SimpleScheduler`` (backward compat)
  - ``Scheduler``: Alias for ``LanceScheduler`` (backward compat)
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

try:
    from croniter import croniter  # type: ignore[import-untyped]
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_HARNESS_ROOT = Path(__file__).resolve().parent

_DEFAULT_SIMPLE_JOBS_PATH = str(_HARNESS_ROOT / "scheduler_jobs.json")
_DEFAULT_LANCE_JOBS_PATH = str(
    _HARNESS_ROOT / "orchestrator" / "scheduler_jobs.yaml",
)


# ---------------------------------------------------------------------------
# Unified ScheduledJob dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScheduledJob:
    """Unified scheduled job supporting both SimpleScheduler and LanceScheduler schemas.

    SimpleScheduler fields:
        ``cron_expr``, ``task_description``, ``run_count``, ``created_at``
    LanceScheduler fields:
        ``trigger``, ``trigger_value``, ``command``, ``max_retries``
    Common fields:
        ``name``, ``enabled``, ``last_run``, ``next_run``
    """

    name: str

    # -- SimpleScheduler fields --
    cron_expr: str = ""
    task_description: str = ""
    run_count: int = 0
    created_at: str = ""

    # -- LanceScheduler fields --
    trigger: str = ""
    trigger_value: str = ""
    command: str = ""
    max_retries: int = 5

    # -- Common fields --
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, omitting empty fields for cleaner output."""
        d = asdict(self)
        # Keep name + enabled even if empty-ish; drop empty strings otherwise
        return {k: v for k, v in d.items() if k in ("name", "enabled") or v not in ("", [], {}, 0, None)}  # type: ignore[comparison-overlap]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledJob":
        """Create from dictionary, filling defaults for missing keys."""
        return cls(
            name=data.get("name", ""),
            cron_expr=data.get("cron_expr", ""),
            task_description=data.get("task_description", ""),
            run_count=data.get("run_count", 0),
            created_at=data.get("created_at", ""),
            trigger=data.get("trigger", ""),
            trigger_value=data.get("trigger_value", ""),
            command=data.get("command", ""),
            max_retries=data.get("max_retries", 5),
            enabled=data.get("enabled", True),
            last_run=data.get("last_run", ""),
            next_run=data.get("next_run", ""),
        )


# ---------------------------------------------------------------------------
# BaseScheduler — abstract interface
# ---------------------------------------------------------------------------


class BaseScheduler(ABC):
    """Abstract base scheduler defining the common job-management API."""

    @abstractmethod
    def add_job(self, *args: Any, **kwargs: Any) -> ScheduledJob:
        """Register a new job.

        Concrete subclasses define their own signature
        (e.g. ``add_job(name, cron_expr, task_description)`` or
        ``add_job(name, trigger, trigger_value, command, ...)``).
        """

    @abstractmethod
    def remove_job(self, name: str) -> bool:
        """Remove a job by name.  Returns ``True`` if the job was removed."""

    @abstractmethod
    def list_jobs(self) -> List[ScheduledJob]:
        """Return all registered jobs."""

    @abstractmethod
    def get_job(self, name: str) -> Optional[ScheduledJob]:
        """Return a specific job by name, or ``None``."""

    @abstractmethod
    def stop(self) -> None:
        """Signal the scheduler to stop (thread-safe)."""


# ---------------------------------------------------------------------------
# JobStore mixin — persistence helpers
# ---------------------------------------------------------------------------


class JobStore:
    """Mixin for JSON / YAML persistence with auto-format detection.

    Requires the host class to have:
      - ``_jobs_path: str``
      - ``_jobs: Dict[str, ScheduledJob]``

    Provides helper methods:
      - ``_load_jobs()``, ``_save_jobs()``, ``_ensure_jobs_file()``
      - ``_detect_format()``, ``_read_file()``, ``_write_file()``
      - ``_serialize_jobs()``, ``_deserialize_jobs()`` (overridable)
    """

    _jobs_path: str = ""
    _jobs: Dict[str, ScheduledJob] = {}

    # ------------------------------------------------------------------
    # Public persistence API
    # ------------------------------------------------------------------

    def _load_jobs(self) -> None:
        """Load jobs from the persistence file."""
        try:
            if not Path(self._jobs_path).is_file():
                self._ensure_jobs_file()
                return
            data = self._read_file()
            if data is None:
                data = self._default_empty_data()
            self._deserialize_jobs(data)
            logger.debug("Loaded %d jobs from %s", len(self._jobs), self._jobs_path)
        except Exception as exc:
            logger.warning("Failed to load jobs from %s: %s", self._jobs_path, exc)

    def _save_jobs(self) -> None:
        """Save jobs to the persistence file."""
        try:
            self._ensure_jobs_file()
            data = self._serialize_jobs()
            self._write_file(data)
        except Exception as exc:
            logger.warning("Failed to save jobs to %s: %s", self._jobs_path, exc)

    def _ensure_jobs_file(self) -> None:
        """Create the jobs file parent directory and file if missing."""
        jobs_path = Path(self._jobs_path)
        parent = jobs_path.parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
        if not jobs_path.is_file():
            self._write_file(self._default_empty_data())

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    def _detect_format(self) -> str:
        """Detect file format from extension: ``'json'`` or ``'yaml'``."""
        ext = Path(self._jobs_path).suffix.lower()
        if ext in (".yaml", ".yml"):
            return "yaml"
        return "json"

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _read_file(self) -> Any:
        """Read and parse the jobs file (JSON or YAML)."""
        fmt = self._detect_format()
        with open(self._jobs_path, "r", encoding="utf-8") as f:
            if fmt == "yaml":
                import yaml  # type: ignore[import-untyped]
                return yaml.safe_load(f) or {}
            return json.load(f)

    def _write_file(self, data: Any) -> None:
        """Write *data* to the jobs file (JSON or YAML)."""
        fmt = self._detect_format()
        with open(self._jobs_path, "w", encoding="utf-8") as f:
            if fmt == "yaml":
                import yaml
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Serialization hooks — override in concrete implementations
    # ------------------------------------------------------------------

    def _serialize_jobs(self) -> Any:
        """Serialize jobs to a storable structure (override as needed)."""
        return [j.to_dict() for j in self._jobs.values()]

    def _deserialize_jobs(self, data: Any) -> None:
        """Deserialize jobs from a loaded structure (override as needed).

        Default implementation handles both ``list[dict]`` and
        ``dict[name, dict]`` formats (the two historical JSON formats).
        """
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

    def _default_empty_data(self) -> Any:
        """Return the empty data structure (override as needed)."""
        return []


# ---------------------------------------------------------------------------
# SimpleScheduler  —  cron-based, JSON persistence
# ---------------------------------------------------------------------------


class SimpleScheduler(BaseScheduler, JobStore):
    """Cron-based task scheduler with JSON persistence.

    Uses ``croniter`` for cron expression parsing when available.
    Provides a blocking :meth:`run_loop` for the main event loop.

    Default jobs file: ``harness/scheduler_jobs.json``
    """

    def __init__(self, jobs_path: str = "") -> None:
        self._jobs_path: str = jobs_path or _DEFAULT_SIMPLE_JOBS_PATH
        self._jobs: Dict[str, ScheduledJob] = {}
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
        logger.info("Scheduled job '%s': %s (next run: %s)", name, cron_expr, next_run)
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job by name.

        Returns ``True`` if the job was removed, ``False`` if it did not exist.
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
        """Return a specific job by name, or ``None``."""
        return self._jobs.get(name)

    def stop(self) -> None:
        """Signal the scheduler loop to stop at the next check cycle."""
        self._running = False
        logger.info("Scheduler stop requested")

    # ------------------------------------------------------------------
    # Scheduling logic
    # ------------------------------------------------------------------

    def _compute_next_run(self, cron_expr: str) -> str:
        """Compute the next run datetime from a cron expression.

        Returns an ISO-formatted datetime string, or an empty string on failure.
        """
        if HAS_CRONITER:
            try:
                base = datetime.datetime.now(datetime.timezone.utc)
                cron = croniter(cron_expr, base)
                next_dt = cron.get_next(datetime.datetime)
                return next_dt.isoformat()
            except (ValueError, KeyError) as exc:
                logger.warning("Invalid cron expression '%s': %s", cron_expr, exc)
        return ""

    def run_due(self) -> List[str]:
        """Execute all jobs whose scheduled time has passed.

        Returns a list of job names that were executed.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        executed: List[str] = []

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
        logger.info(
            "Executing scheduled job '%s': %s",
            job.name,
            job.task_description,
        )

    def run_loop(self, poll_interval: Optional[int] = None) -> None:
        """Start the scheduler loop, checking for due jobs periodically.

        This method **blocks indefinitely**.  Set *poll_interval* to override
        the default 60-second check interval.

        To stop the loop, call :meth:`stop` from another thread.
        """
        if poll_interval is not None:
            self._poll_interval = poll_interval

        self._running = True
        logger.info(
            "Scheduler loop started (poll interval: %ds)", self._poll_interval,
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


# ---------------------------------------------------------------------------
# LanceScheduler  —  schedule-library-based, YAML persistence, LanceDB logging
# ---------------------------------------------------------------------------


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
        self._jobs_path: str = jobs_path or _DEFAULT_LANCE_JOBS_PATH
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

        logger.info(
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

    def stop(self) -> None:
        """Signal the scheduler loop to stop."""
        self._running = False
        logger.info("Scheduler stopping...")

    # ------------------------------------------------------------------
    # Serialization overrides — YAML uses {"jobs": [...]} format
    # ------------------------------------------------------------------

    def _serialize_jobs(self) -> Dict[str, Any]:
        return {"jobs": [j.to_dict() for j in self._jobs.values()]}

    def _deserialize_jobs(self, data: Dict[str, Any]) -> None:
        for jd in data.get("jobs", []):
            job = ScheduledJob.from_dict(jd)
            self._jobs[job.name] = job

    def _default_empty_data(self) -> Dict[str, Any]:
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

    def _scheduler_loop(self) -> None:
        """Main scheduler loop — evaluates triggers and runs jobs."""
        # Lazy-import schedule so it's optional at class-import time
        try:
            import schedule as _schedule_lib  # type: ignore[import-untyped]
            self._schedule = _schedule_lib
        except ImportError:
            logger.error(
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
                        logger.warning("Unsupported interval unit: %s", unit)
                else:
                    logger.warning("Invalid interval format: %s", job.trigger_value)

            elif job.trigger == "once":
                _sched.every().day.at("00:00").do(
                    self._execute_job_once, job_name=job.name,
                )

            elif job.trigger == "cron":
                self._register_cron(_sched, job)

            logger.debug("Registered job '%s' with schedule lib", job.name)
        except Exception as exc:
            logger.error("Failed to register job '%s': %s", job.name, exc)

    def _register_cron(self, sched: Any, job: ScheduledJob) -> None:
        """Map a cron expression to schedule library syntax (best-effort)."""
        cron_parts = job.trigger_value.strip().split()
        if len(cron_parts) < 5:
            logger.warning("Invalid cron expression: %s", job.trigger_value)
            return

        minute = cron_parts[0]
        hour = cron_parts[1]
        day_of_week = cron_parts[4] if len(cron_parts) > 4 else "*"

        if minute == "*" and hour == "*" and day_of_week == "*":
            sched.every(1).minutes.do(self._execute_job, job_name=job.name)
        elif minute == "0" and hour != "*" and day_of_week == "*":
            sched.every().day.at(f"{hour}:00").do(
                self._execute_job, job_name=job.name,
            )
        elif minute == "0" and hour != "*" and day_of_week != "*":
            sched.every().day.at(f"{hour}:00").do(
                self._execute_job, job_name=job.name,
            )
        else:
            logger.warning(
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

        logger.info("Executing job '%s': %s", job_name, job.command)
        start = time.time()
        status = "success"
        error_msg = ""

        try:
            import shlex as _shlex
            import subprocess as _subprocess

            cmd_list = _shlex.split(job.command)
            result = _subprocess.run(
                cmd_list, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                status = "failed"
                error_msg = result.stderr[-500:] if result.stderr else "exit code != 0"
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)

        elapsed = time.time() - start
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Update job state
        with self._lock:
            j = self._jobs.get(job_name)
            if j:
                j.last_run = now

        # Log to LanceDB
        if job is not None:
            self._log_execution(job_name, job, status, elapsed, error_msg, now)

        logger.info("Job '%s' %s (%.3fs)", job_name, status, elapsed)

    def _execute_job_once(self, job_name: str) -> None:
        """Execute a once-type job and disable it afterward."""
        self._execute_job(job_name)
        with self._lock:
            job = self._jobs.get(job_name)
            if job:
                job.enabled = False
                self._save_jobs()
                logger.info(
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
            logger.debug(
                "LanceDB logging unavailable (numpy or lance_vector_store)",
            )
            return

        metadata: Dict[str, Any] = {
            "job_name": job_name,
            "trigger": job.trigger,
            "status": status,
            "duration_ms": int(duration_ms * 1000),
            "error": error[:500] if error else "",
            "timestamp": timestamp,
        }

        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
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
            logger.warning(
                "Failed to log scheduler execution: %s", exc,
            )


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

#: Alias for :class:`SimpleScheduler` — the name used in the original
#: ``harness/scheduler.py`` module.
TaskScheduler = SimpleScheduler

#: Alias for :class:`LanceScheduler` — the name used in the original
#: ``harness/orchestrator/scheduler.py`` module.
Scheduler = LanceScheduler
