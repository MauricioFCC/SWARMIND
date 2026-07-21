"""
Scheduler — thin wrapper around the unified :mod:`harness.scheduler`.

This module now re-exports :class:`~harness.scheduler.Scheduler` (which is
:class:`~harness.scheduler.LanceScheduler`) and
:class:`~harness.scheduler.ScheduledJob` from the unified scheduler at
``harness/scheduler.py``.

All code importing from ``harness.orchestrator.scheduler`` continues to work
without modification.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Re-export the unified implementations with their original names.
#   Scheduler    → LanceScheduler  (was Scheduler in orchestrator)
#   ScheduledJob → ScheduledJob    (unified)
from harness.scheduler import (  # noqa: F401  — public re-export
    LanceScheduler as Scheduler,
)

logger = logging.getLogger(__name__)

# Keep module-level path constants available for any code that may reference
# them via ``harness.orchestrator.scheduler.SCHEDULER_JOBS_PATH``, etc.
HARNESS_ROOT = Path(__file__).resolve().parent.parent  # harness/
SCHEDULER_JOBS_PATH = HARNESS_ROOT / "orchestrator" / "scheduler_jobs.yaml"
