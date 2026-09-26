"""Tests para restrictor markdown + read-guard + misbehavior + dream-replay (ADR-0088).

SerpApi (-74%: md 6.4k vs JSON 24.7k, organic -95%) -> restrictor que deja
contenido organico. Shunt (Spotify: 90% tokens era mover contexto) ->
read-guard topa lecturas grandes con spill a disco. OpenAI 6 conductas ->
misbehavior guard pre-tool-call. Dream-RSI -> dream-replay offline de
intentos ok/fail contra codigo fijo.
"""

import json

import pytest

from harness.evolve_loop.dream_replay import (
    ReplaySummary,
    dream_replay,
)
from harness.orchestrator.content_restrictor import (
    restrict_markdown,
)
from harness.orchestrator.read_guard import (
    ReadGuard,
)
from harness.security.misbehavior_guard import (
    MisbehaviorReport,
    check_tool_call,
)


def test_restrict_drops_json_noise() -> None:
    """JSON con metadata ruidosa -> solo contenido organico."""
    raw = json.dumps({
        "organic": [{"title": "T", "snippet": "respuesta util"}],
        "ads": [{"title": "compra ya"}],
        "pagination": {"page": 1, "total": 99},
        "related": ["x", "y"],
    })
    out = restrict_markdown(raw)
    assert "respuesta util" in out
    assert "compra ya" not in out
    assert "pagination" not in out
    assert len(out) < len(raw) // 2


def test_restrict_plain_markdown_passthrough() -> None:
    """Markdown sin JSON pasa con limpieza minima."""
    out = restrict_markdown("# Titulo\n\nparrafo util")
    assert "parrafo util" in out


def test_restrict_empty_raises() -> None:
    """Vacio falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        restrict_markdown("   ")


def test_read_guard_small_passthrough() -> None:
    """Lectura chica pasa integra."""
    guard = ReadGuard(max_chars=1000)
    out = guard.read("abc\n" * 10)
    assert out.truncated is False
    assert "abc" in out.inline


def test_read_guard_big_spills_to_artifact() -> None:
    """Lectura grande -> preview + handle (shunt, no mover contexto)."""
    guard = ReadGuard(max_chars=1000)
    big = "linea de codigo\n" * 500
    out = guard.read(big)
    assert out.truncated is True
    assert out.handle
    assert len(out.inline) < len(big) // 2
    full = guard.retrieve(out.handle)
    assert full == big


def test_read_guard_invalid_limit_raises() -> None:
    """Limite no positivo falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        ReadGuard(max_chars=0)


def test_misbehavior_detects_exposed_creds() -> None:
    """Credenciales expuestas en args -> BLOQUEO."""
    report = check_tool_call("bash", {"cmd": "curl -H 'key: sk-abc123' api.com"})
    assert isinstance(report, MisbehaviorReport)
    assert report.blocked is True
    assert "credencial" in report.reason.lower()


def test_misbehavior_detects_upload() -> None:
    """Subida de archivos a externo -> BLOQUEO (exfiltracion)."""
    report = check_tool_call("upload", {"file": "clientes.csv", "to": "https://x.io"})
    assert report.blocked is True


def test_misbehavior_allows_clean_call() -> None:
    """Llamada limpia -> permitida."""
    report = check_tool_call("bash", {"cmd": "pytest -q"})
    assert report.blocked is False


def test_misbehavior_empty_tool_raises() -> None:
    """Tool vacia falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        check_tool_call("", {})


def test_dream_replay_counts() -> None:
    """Replay offline: compara salidas viejas vs codigo fijo."""
    traces = [
        {"id": "t1", "input": "a", "old_output": "x", "new_output": "x"},
        {"id": "t2", "input": "b", "old_output": "x", "new_output": "y"},
    ]
    summary = dream_replay(traces)
    assert isinstance(summary, ReplaySummary)
    assert summary.total == 2
    assert summary.improved == 1
    assert summary.regressed == 0
    assert summary.unchanged == 1


def test_dream_replay_empty() -> None:
    """Sin trazas: ceros, sin error."""
    summary = dream_replay([])
    assert summary.total == 0
