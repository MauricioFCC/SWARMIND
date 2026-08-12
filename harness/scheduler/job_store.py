"""Mixin ``JobStore`` — persistencia JSON/YAML con auto-detección de formato.

Extracción mecánica desde ``harness/scheduler.py`` (sin cambios de lógica).

El logger se resuelve vía el paquete en tiempo de llamada
(``import harness.scheduler as _pkg``) para que
``patch("harness.scheduler.logger")`` siga funcionando idéntico.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import harness.scheduler as _pkg

from .scheduled_job import ScheduledJob


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

    _jobs_path: ClassVar[str] = ""
    _jobs: ClassVar[dict[str, ScheduledJob]] = {}

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
            _pkg.logger.debug("Loaded %d jobs from %s", len(self._jobs), self._jobs_path)
        except Exception as exc:  # noqa: BLE001
            _pkg.logger.warning("Failed to load jobs from %s: %s", self._jobs_path, exc)

    def _save_jobs(self) -> None:
        """Save jobs to the persistence file."""
        try:
            self._ensure_jobs_file()
            data = self._serialize_jobs()
            self._write_file(data)
        except Exception as exc:  # noqa: BLE001
            _pkg.logger.warning("Failed to save jobs to %s: %s", self._jobs_path, exc)

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
