"""Dataclass unificada ``ScheduledJob`` (schemas SimpleScheduler y LanceScheduler).

Extracción mecánica desde ``harness/scheduler.py`` (sin cambios de lógica).

SimpleScheduler fields:
    ``cron_expr``, ``task_description``, ``run_count``, ``created_at``
LanceScheduler fields:
    ``trigger``, ``trigger_value``, ``command``, ``max_retries``
Common fields:
    ``name``, ``enabled``, ``last_run``, ``next_run``
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass
from typing import Any


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
            self.created_at = datetime.datetime.now(datetime.UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary, omitting empty fields for cleaner output."""
        d = asdict(self)
        # Keep name + enabled even if empty-ish; drop empty strings otherwise
        return {k: v for k, v in d.items() if k in ("name", "enabled") or v not in ("", [], {}, 0, None)}  # type: ignore[comparison-overlap]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledJob:
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
