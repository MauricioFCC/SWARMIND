"""Tests para artifact_store — eviction de tool results a disco (ADR-0074).

Frontera 2026 (artifact-backed eviction, tier 1): tool result grande se
persiste a disco y al contexto solo va {resumen + primeras lineas + handle};
el agente puede recuperar el contenido completo por offset. Reduce el
contexto sin perder acceso (a diferencia del observation masking puro).
"""

import pytest

from harness.memory_rag.artifact_store import (
    DEFAULT_THRESHOLD_CHARS,
    HEAD_LINES,
    ArtifactStore,
)


def test_small_result_passes_through() -> None:
    """Resultados bajo el umbral no se persisten (pasan integros)."""
    store = ArtifactStore(cache_dir=None)
    out = store.evict("ok")
    assert out.persisted is False
    assert out.inline == "ok"


def test_large_result_persisted_with_summary_and_handle() -> None:
    """Resultado grande -> {summary, primeras lineas, handle} en contexto."""
    store = ArtifactStore(cache_dir=None)
    big = "linea\n" * 800
    out = store.evict(big)
    assert out.persisted is True
    assert out.handle in out.inline
    assert out.inline.count("\n") >= HEAD_LINES
    assert "artifact" in out.inline.lower() or "handle" in out.inline.lower()


def test_retrieve_by_handle_full_and_offset() -> None:
    """El handle recupera el contenido completo o desde offset."""
    store = ArtifactStore(cache_dir=None)
    content = "uno\ndos\ntres\ncuatro"
    out = store.evict(content, force=True)
    assert out.persisted is True
    full = store.retrieve(out.handle)
    assert full == content
    tail = store.retrieve(out.handle, offset=1)
    assert tail == "dos\ntres\ncuatro"


def test_retrieve_unknown_handle_raises() -> None:
    """Handle inexistente falla accionable (sin swallow)."""
    store = ArtifactStore(cache_dir=None)
    with pytest.raises(Exception, match="WHAT"):
        store.retrieve("no-existe-0000")


def test_force_persists_below_threshold() -> None:
    """force=True persiste aunque el contenido sea pequeno."""
    store = ArtifactStore(cache_dir=None)
    out = store.evict("corto", force=True)
    assert out.persisted is True


def test_threshold_default_documented() -> None:
    """Umbral default >= 4000 chars (compaction-friendly)."""
    assert DEFAULT_THRESHOLD_CHARS >= 4000


def test_disk_roundtrip(tmp_path) -> None:
    """Con cache_dir real, el JSON se escribe y se lee byte-exacto."""
    store = ArtifactStore(cache_dir=tmp_path)
    big = "x" * 6000
    out = store.evict(big)
    assert out.persisted is True
    assert store.retrieve(out.handle) == big
