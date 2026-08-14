"""ABC ``BaseScheduler`` — interfaz abstracta del API común de schedulers.

Extracción mecánica desde ``harness/scheduler.py`` (sin cambios de lógica).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .scheduled_job import ScheduledJob


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
    def list_jobs(self) -> list[ScheduledJob]:
        """Return all registered jobs."""

    @abstractmethod
    def get_job(self, name: str) -> ScheduledJob | None:
        """Return a specific job by name, or ``None``."""

    @abstractmethod
    def stop(self) -> None:
        """Signal the scheduler to stop (thread-safe)."""
