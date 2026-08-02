"""
Registro estructurado en JSON para el Task Orchestrator.

Proporciona la clase StructuredLogRecord que emite logs con formato
estructurado (timestamp, level, module, event, session_id, message y
campos extra) para facilitar la monitorización centralizada.

Uso:
    StructuredLogRecord.info("evento", "mensaje", session_id="abc-123")
    StructuredLogRecord.error("fallo", "algo salió mal", error_code=42)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class StructuredLogRecord:
    """
    Structured log record as JSON.

    Cada entrada incluye: timestamp, level, module, session_id (opcional),
    event, y detalles específicos.
    """

    def __init__(
        self,
        event: str,
        level: str = "INFO",
        session_id: str | None = None,
        message: str = "",
        **extra,
    ) -> None:
        self._data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "module": "task_orchestrator",
            "event": event,
            "session_id": session_id or "",
            "message": message,
            **extra,
        }

    def log(self, logger_instance: logging.Logger) -> None:
        level_map = {
            "DEBUG": logger_instance.debug,
            "INFO": logger_instance.info,
            "WARNING": logger_instance.warning,
            "ERROR": logger_instance.error,
            "CRITICAL": logger_instance.critical,
        }
        level_map.get(self._data["level"], logger_instance.info)(
            "%s", json.dumps(self._data, ensure_ascii=False)
        )

    @staticmethod
    def info(event: str, message: str = "", session_id: str | None = None, **extra):
        extra.pop("level", None)
        StructuredLogRecord(event, "INFO", session_id, message, **extra).log(logger)

    @staticmethod
    def warning(event: str, message: str = "", session_id: str | None = None, **extra):
        extra.pop("level", None)
        StructuredLogRecord(event, "WARNING", session_id, message, **extra).log(logger)

    @staticmethod
    def error(event: str, message: str = "", session_id: str | None = None, **extra):
        extra.pop("level", None)
        StructuredLogRecord(event, "ERROR", session_id, message, **extra).log(logger)

    @staticmethod
    def debug(event: str, message: str = "", session_id: str | None = None, **extra):
        extra.pop("level", None)
        StructuredLogRecord(event, "DEBUG", session_id, message, **extra).log(logger)


__all__ = ["StructuredLogRecord"]
