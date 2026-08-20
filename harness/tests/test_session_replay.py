"""Tests de SessionReplay — reconstruccion del historial de sesion desde el log.

Formato usado: log JSON por linea (derivado de harness/observability/logging.py)
con timestamp/level/logger/message + extra_fields opcionales con session_id y role.
Los fixtures escriben el log en tempfile (sin red).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.observability.session_replay import (
    DEFAULT_LOG_PATH,
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
    SessionNotFoundError,
    SessionReplay,
)

# ===========================================================================
# Fixtures
# ===========================================================================


def _log_line(
    message: str,
    session_id: str,
    role: str = "system",
    timestamp: str = "2026-08-17 10:00:00,000",
    correlation_id: str = "corr-1",
    level: str = "INFO",
    session_in_extra: bool = False,
) -> str:
    """Construye una linea JSON en el formato real de logging.py."""
    record: dict = {
        "timestamp": timestamp,
        "level": level,
        "logger": "harness.test",
        "message": message,
        "module": "test",
        "function": "run",
        "line": 42,
        "correlation_id": correlation_id,
        "extra_fields": {"session_id": session_id, "role": role},
    }
    if not session_in_extra:
        record["session_id"] = session_id
        record["extra_fields"] = {"role": role}
    return json.dumps(record, ensure_ascii=False)


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    """Log JSON por linea con dos sesiones y timestamps desordenados."""
    lines = [
        # Sesion s1 (desordenada a proposito: tool antes que user)
        _log_line("resultado de la tool", "s1", role=ROLE_TOOL, timestamp="2026-08-17 10:00:03,000"),
        _log_line("mensaje del usuario", "s1", role=ROLE_USER, timestamp="2026-08-17 10:00:01,000"),
        _log_line("respuesta del asistente", "s1", role=ROLE_ASSISTANT, timestamp="2026-08-17 10:00:02,000"),
        # Sesion s2 (para verificar filtrado)
        _log_line("otra sesion", "s2", role=ROLE_USER, timestamp="2026-08-17 10:00:05,000"),
        # Evento con session_id dentro de extra_fields
        _log_line(
            "evento con sid en extra", "s1", role=ROLE_TOOL,
            timestamp="2026-08-17 10:00:04,000", session_in_extra=True,
        ),
        # Linea basura no-JSON (debe ignorarse)
        "this is not json @@@",
        # Linea JSON sin session_id (debe filtrarse)
        json.dumps({"timestamp": "2026-08-17 10:00:06,000", "level": "INFO", "message": "sin sesion"}),
    ]
    path = tmp_path / "session.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def replay(log_file: Path) -> SessionReplay:
    """SessionReplay apuntando al log de fixture."""
    return SessionReplay(log_source=log_file)


# ===========================================================================
# replay
# ===========================================================================


class TestReplay:
    """Tests de replay()."""

    def test_replay_filters_by_session(self, replay: SessionReplay) -> None:
        """replay devuelve solo eventos de la sesion indicada."""
        events = replay.replay("s1")
        assert len(events) == 4
        assert all(e["session_id"] == "s1" for e in events)

    def test_replay_sorts_by_timestamp(self, replay: SessionReplay) -> None:
        """replay ordena cronologicamente por timestamp."""
        events = replay.replay("s1")
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)

    def test_replay_normalizes_role_and_content(self, replay: SessionReplay) -> None:
        """Eventos normalizados exponen role/content estables."""
        events = replay.replay("s1")
        first = events[0]
        assert first["role"] == ROLE_USER
        assert first["content"] == "mensaje del usuario"
        assert first["correlation_id"] == "corr-1"

    def test_replay_reads_session_id_from_extra_fields(self, replay: SessionReplay) -> None:
        """session_id dentro de extra_fields tambien se detecta."""
        events = replay.replay("s1")
        content = {e["content"] for e in events}
        assert "evento con sid en extra" in content

    def test_replay_empty_session_returns_empty_list(self, replay: SessionReplay) -> None:
        """Sesion inexistente en el log retorna [] (no lanza)."""
        assert replay.replay("no-existe") == []

    def test_replay_raises_on_empty_session_id(self, replay: SessionReplay) -> None:
        """session_id vacio lanza SessionNotFoundError."""
        with pytest.raises(SessionNotFoundError):
            replay.replay("")
        with pytest.raises(SessionNotFoundError):
            replay.replay("   ")

    def test_replay_missing_log_returns_empty(self, tmp_path: Path) -> None:
        """Log inexistente retorna [] sin fallar."""
        r = SessionReplay(log_source=tmp_path / "missing.log")
        assert r.replay("s1") == []

    def test_replay_ignores_garbage_lines(self, replay: SessionReplay) -> None:
        """Lineas no-JSON no rompen el parseo."""
        events = replay.replay("s1")
        assert len(events) == 4  # la linea basura no cuenta

    def test_replay_log_source_arg_overrides(self, replay: SessionReplay, tmp_path: Path) -> None:
        """log_source pasado a replay sobreescribe el del init."""
        other = tmp_path / "other.log"
        other.write_text(_log_line("solo", "s9", role=ROLE_USER), encoding="utf-8")
        events = replay.replay("s9", log_source=other)
        assert len(events) == 1
        assert events[0]["content"] == "solo"

    def test_replay_default_log_path_constant(self) -> None:
        """Existe un DEFAULT_LOG_PATH documentado."""
        assert isinstance(DEFAULT_LOG_PATH, Path)
        assert DEFAULT_LOG_PATH.name == "swarmind.log"

    def test_replay_ignores_blank_lines(self, tmp_path: Path) -> None:
        """Lineas en blanco se ignoran sin romper el parseo."""
        path = tmp_path / "blank.log"
        path.write_text(
            "\n" + _log_line("uno", "s1", role=ROLE_USER) + "\n\n", encoding="utf-8"
        )
        events = SessionReplay(log_source=path).replay("s1")
        assert len(events) == 1

    def test_replay_handles_unparseable_timestamp(self, tmp_path: Path) -> None:
        """Timestamp no parseable no rompe: el evento se conserva y ordena."""
        path = tmp_path / "badts.log"
        path.write_text(
            _log_line("raro", "s1", role=ROLE_USER, timestamp="no-es-una-fecha"),
            encoding="utf-8",
        )
        events = SessionReplay(log_source=path).replay("s1")
        assert len(events) == 1
        assert events[0]["content"] == "raro"

    def test_replay_event_without_timestamp(self, tmp_path: Path) -> None:
        """Evento sin timestamp se conserva (clave de orden por defecto)."""
        path = tmp_path / "nots.log"
        record = json.loads(_log_line("sin ts", "s1", role=ROLE_USER))
        record.pop("timestamp", None)
        path.write_text(json.dumps(record), encoding="utf-8")
        events = SessionReplay(log_source=path).replay("s1")
        assert len(events) == 1
        assert events[0]["timestamp"] == ""

    def test_replay_log_source_is_directory(self, tmp_path: Path) -> None:
        """Log_source apuntando a un directorio retorna [] sin fallar (OSError)."""
        r = SessionReplay(log_source=tmp_path)
        assert r.replay("s1") == []


# ===========================================================================
# export_json
# ===========================================================================


class TestExportJson:
    """Tests de export_json()."""

    def test_export_json_returns_valid_list(self, replay: SessionReplay) -> None:
        """export_json produce JSON valido con eventos de la sesion."""
        payload = json.loads(replay.export_json("s1"))
        assert isinstance(payload, list)
        assert len(payload) == 4
        assert all("role" in e and "content" in e for e in payload)

    def test_export_json_empty_session(self, replay: SessionReplay) -> None:
        """Sesion sin eventos exporta una lista vacia."""
        assert json.loads(replay.export_json("no-existe")) == []

    def test_export_json_raises_on_empty_id(self, replay: SessionReplay) -> None:
        """export_json hereda el contrato de session_id invalido."""
        with pytest.raises(SessionNotFoundError):
            replay.export_json("")


# ===========================================================================
# export_markdown
# ===========================================================================


class TestExportMarkdown:
    """Tests de export_markdown()."""

    def test_markdown_has_heading(self, replay: SessionReplay) -> None:
        """Markdown incluye el encabezado con el session_id."""
        md = replay.export_markdown("s1")
        assert "# Session Replay: s1" in md
        assert "Eventos: 4" in md

    def test_markdown_alternates_roles(self, replay: SessionReplay) -> None:
        """Markdown agrupa USER/ASSISTANT/TOOL alternados."""
        md = replay.export_markdown("s1")
        assert "## USER" in md
        assert "## ASSISTANT" in md
        assert "## TOOL" in md
        # Orden del contenido segun timeline
        user_pos = md.index("## USER")
        assistant_pos = md.index("## ASSISTANT")
        tool_pos = md.index("## TOOL")
        assert user_pos < assistant_pos < tool_pos

    def test_markdown_includes_content_and_timestamps(self, replay: SessionReplay) -> None:
        """Markdown muestra contenido y timestamp de cada evento."""
        md = replay.export_markdown("s1")
        assert "mensaje del usuario" in md
        assert "2026-08-17 10:00:01,000" in md

    def test_markdown_empty_session(self, replay: SessionReplay) -> None:
        """Sesion sin eventos produce markdown con nota informativa."""
        md = replay.export_markdown("no-existe")
        assert "# Session Replay: no-existe" in md
        assert "Sin eventos" in md

    def test_markdown_raises_on_empty_id(self, replay: SessionReplay) -> None:
        """export_markdown hereda el contrato de session_id invalido."""
        with pytest.raises(SessionNotFoundError):
            replay.export_markdown("")

    def test_markdown_unknown_role_uses_upper_label(self, tmp_path: Path) -> None:
        """Rol no mapeado se renderiza con la etiqueta en mayusculas."""
        path = tmp_path / "unknown_role.log"
        path.write_text(
            _log_line("mensaje debug", "s1", role="debug"), encoding="utf-8"
        )
        md = SessionReplay(log_source=path).export_markdown("s1")
        assert "## DEBUG" in md
        assert "mensaje debug" in md

    def test_markdown_event_without_timestamp(self, tmp_path: Path) -> None:
        """Evento sin timestamp se renderiza sin corchetes de tiempo."""
        path = tmp_path / "nots_md.log"
        record = json.loads(_log_line("sin tiempo", "s1", role=ROLE_USER))
        record.pop("timestamp", None)
        path.write_text(json.dumps(record), encoding="utf-8")
        md = SessionReplay(log_source=path).export_markdown("s1")
        assert "- sin tiempo" in md
