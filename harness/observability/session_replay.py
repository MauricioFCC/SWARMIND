"""SessionReplay — Reconstruccion del historial de una sesion desde el log.

Formato de log esperado (derivado de harness/observability/logging.py):
log JSON por linea con claves timestamp, level, logger, message, module,
function, line, y opcionalmente correlation_id/trace_id/span_id, mas un
dict extra_fields que puede contener session_id y role.

Ejemplo de linea:
{"timestamp": "2026-08-17 10:00:00,123", "level": "INFO",
 "logger": "harness.foo", "message": "operation ok",
 "correlation_id": "abc",
 "extra_fields": {"session_id": "s-1", "role": "user"}}

El replay filtra por session_id (clave directa o dentro de extra_fields),
normaliza cada evento a {timestamp, role, content, session_id,
correlation_id, level} y los ordena cronologicamente por timestamp.

Si session_id es vacio/None se lanza SessionNotFoundError (contrato de API
roto). Si la sesion no tiene eventos en el log se retorna [] (consistente
con el estilo del repo: get_session -> None, discover_all -> 0).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path("logs/swarmind.log")

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"
ROLE_SYSTEM = "system"
ROLE_DEFAULT = ROLE_SYSTEM

ROLE_LABELS = {
    ROLE_USER: "USER",
    ROLE_ASSISTANT: "ASSISTANT",
    ROLE_TOOL: "TOOL",
    ROLE_SYSTEM: "SYSTEM",
}

_EPOCH = datetime.min.replace(tzinfo=UTC)


class SessionNotFoundError(Exception):
    """Error por session_id invalido (vacio/None).

    WHAT: no se puede reconstruir la sesion porque el identificador es
    invalido (contrato de API roto).
    WHY: session_id vacio o None no identifica ninguna sesion.
    WHERE: lanzado por SessionReplay.replay/export_markdown/export_json.
    """

    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"SessionNotFoundError: session_id={session_id!r} es invalido "
            "(vacio o None). WHY: no identifica ninguna sesion. "
            "WHERE: SessionReplay.replay."
        )


class SessionReplay:
    """Reconstruye el historial de una sesion desde un log JSON por linea.

    Args:
        log_source: Ruta al archivo de log (default: logs/swarmind.log).
    """

    def __init__(self, log_source: Path | None = None) -> None:
        """Inicializa el replay con la fuente de log.

        Args:
            log_source: Ruta al log. Si None, usa DEFAULT_LOG_PATH.
        """
        self._log_source: Path = log_source or DEFAULT_LOG_PATH

    def replay(
        self, session_id: str, log_source: Path | None = None
    ) -> list[dict[str, Any]]:
        """Reconstruye los eventos de una sesion ordenados por timestamp.

        Args:
            session_id: ID de la sesion a reconstruir.
            log_source: Ruta alternativa al log (sobreescribe la del init).

        Returns:
            Lista de eventos normalizados (timestamp, role, content,
            session_id, correlation_id, level) ordenados cronologicamente.

        Raises:
            SessionNotFoundError: si session_id es vacio o None.
        """
        if not session_id or not session_id.strip():
            raise SessionNotFoundError(session_id)
        source = log_source or self._log_source
        events = [
            self._normalize(record)
            for record in self._read_records(source)
            if self._record_matches(record, session_id)
        ]
        return sorted(events, key=self._sort_key)

    def export_markdown(
        self, session_id: str, log_source: Path | None = None
    ) -> str:
        """Renderiza la sesion a Markdown legible (USER/ASSISTANT/TOOL).

        Args:
            session_id: ID de la sesion a exportar.
            log_source: Ruta alternativa al log (sobreescribe la del init).

        Returns:
            String Markdown con eventos agrupados por rol, listo para
            usarse como contexto de modelo.

        Raises:
            SessionNotFoundError: si session_id es vacio o None.
        """
        events = self.replay(session_id, log_source)
        return self._render_markdown(session_id, events)

    def export_json(
        self, session_id: str, log_source: Path | None = None
    ) -> str:
        """Exporta la sesion como JSON (lista de eventos normalizados).

        Args:
            session_id: ID de la sesion a exportar.
            log_source: Ruta alternativa al log (sobreescribe la del init).

        Returns:
            String JSON con la lista de eventos de la sesion.

        Raises:
            SessionNotFoundError: si session_id es vacio o None.
        """
        events = self.replay(session_id, log_source)
        return json.dumps(events, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _read_records(self, source: Path) -> list[dict[str, Any]]:
        """Lee y parsea las lineas JSON del log.

        Args:
            source: Ruta del archivo de log.

        Returns:
            Lista de records JSON (dicts). Lineas vacias, no-JSON o el
            archivo inexistente se manejan sin fallar.
        """
        path = Path(source)
        if not path.exists():
            logger.warning(
                "SessionReplay: log inexistente %s (WHERE: _read_records)",
                path,
            )
            return []
        records: list[dict[str, Any]] = []
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(
                "SessionReplay: no se pudo leer %s: %s (WHERE: _read_records)",
                path, exc,
            )
            return []
        for raw in raw_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.debug(
                    "SessionReplay: linea no-JSON ignorada: %s (%s)",
                    line[:60], exc,
                )
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

    @staticmethod
    def _record_matches(record: dict[str, Any], session_id: str) -> bool:
        """Verifica si un record del log pertenece a la sesion.

        Args:
            record: Record JSON del log.
            session_id: ID de sesion buscado.

        Returns:
            True si el record tiene session_id como clave directa o
            dentro de extra_fields.
        """
        extra = record.get("extra_fields")
        extra_sid = extra.get("session_id") if isinstance(extra, dict) else None
        return record.get("session_id") == session_id or extra_sid == session_id

    @staticmethod
    def _normalize(record: dict[str, Any]) -> dict[str, Any]:
        """Normaliza un record a un evento con claves estables.

        Args:
            record: Record JSON del log.

        Returns:
            Evento normalizado con timestamp, role, content, session_id,
            correlation_id y level.
        """
        extra = record.get("extra_fields")
        extra = extra if isinstance(extra, dict) else {}
        role = record.get("role") or extra.get("role") or ROLE_DEFAULT
        session_id = record.get("session_id") or extra.get("session_id", "")
        return {
            "timestamp": record.get("timestamp", ""),
            "role": str(role),
            "content": record.get("message", ""),
            "session_id": str(session_id),
            "correlation_id": record.get("correlation_id", ""),
            "level": record.get("level", ""),
        }

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        """Parsea un timestamp del log a datetime.

        Args:
            value: Timestamp en formato ISO o "YYYY-MM-DD HH:MM:SS,mmm".

        Returns:
            datetime o None si el valor no se puede parsear.
        """
        if not value:
            return None
        normalized = value.replace(",", ".").replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            logger.debug("SessionReplay: timestamp no parseable: %s", value)
            return None

    def _sort_key(self, event: dict[str, Any]) -> tuple[datetime, str]:
        """Clave de ordenacion cronologica para un evento.

        Args:
            event: Evento normalizado.

        Returns:
            (datetime, timestamp raw) compatible con sorted().
        """
        parsed = self._parse_timestamp(str(event.get("timestamp", "")))
        return (parsed or _EPOCH, str(event.get("timestamp", "")))

    def _render_markdown(
        self, session_id: str, events: list[dict[str, Any]]
    ) -> str:
        """Renderiza eventos a Markdown agrupado por rol consecutivo.

        Args:
            session_id: ID de la sesion.
            events: Eventos normalizados y ordenados.

        Returns:
            String Markdown con bloques por rol (USER/ASSISTANT/TOOL...).
        """
        lines = [f"# Session Replay: {session_id}", "", f"Eventos: {len(events)}", ""]
        if not events:
            lines.append("_Sin eventos registrados para esta sesion en el log._")
            return "\n".join(lines)
        current_role: str | None = None
        for event in events:
            role = str(event.get("role", ROLE_DEFAULT))
            label = ROLE_LABELS.get(role, role.upper() or "INFO")
            if label != current_role:
                lines.extend(["", f"## {label}"])
                current_role = label
            timestamp = event.get("timestamp", "")
            content = str(event.get("content", ""))
            if timestamp:
                lines.append(f"- [{timestamp}] {content}")
            else:
                lines.append(f"- {content}")
        return "\n".join(lines)